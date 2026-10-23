$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction Stop).Source
Push-Location $root
try {
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed --name ScatterLauncher --version-file tools/launcher-version.txt --icon assets/scattermacro.ico --add-data 'assets;assets' --add-data 'catalog.json;.' main.py
    if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed' }
    # The bootloader searches _internal first. Python's older VC runtime must
    # not win over the runtime shipped with this exact Qt distribution.
    $qt = & $python -c "import pathlib, PySide6; print(pathlib.Path(PySide6.__file__).parent)"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot locate Qt runtime' }
    foreach ($dll in Get-ChildItem -LiteralPath $qt -File | Where-Object { $_.Name -match '^(msvcp140|vcruntime140).*\.dll$' }) {
        Copy-Item -LiteralPath $dll.FullName -Destination (Join-Path $root ('dist\ScatterLauncher\_internal\' + $dll.Name)) -Force
    }
    # Qt uses Windows' unversioned ICU API. A third-party icuuc.dll discovered
    # on PATH exposes suffixed symbols instead and prevents QtCore loading.
    $icu = Join-Path $root 'dist\ScatterLauncher\_internal\icuuc.dll'
    if (Test-Path -LiteralPath $icu) { Remove-Item -LiteralPath $icu }
    & (Join-Path $PSScriptRoot 'TestLauncherBuild.ps1')
    Compress-Archive -Path dist/ScatterLauncher -DestinationPath dist/ScatterLauncher-0.4.2-windows.zip -Force
    $archive = Join-Path $root 'dist\ScatterLauncher-0.4.2-windows.zip'
    $hashFile = Join-Path $root 'dist\payload.sha256'
    [IO.File]::WriteAllText($hashFile, (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant())
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    & $compiler /nologo /target:winexe /platform:anycpu /reference:System.Windows.Forms.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll "/win32icon:$root\assets\scattermacro.ico" "/resource:$archive,payload.zip" "/resource:$hashFile,payload.sha256" "/out:$root\dist\ScatterMacro.exe" "$root\tools\LauncherBootstrap.cs"
    if ($LASTEXITCODE -ne 0) { throw 'Standalone launcher build failed' }
} finally {
    Pop-Location
}
