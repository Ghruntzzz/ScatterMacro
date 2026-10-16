$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
Push-Location $root
try {
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed --name ScatterLauncher --icon assets/scattermacro.ico --add-data 'assets;assets' --add-data 'catalog.json;.' main.py
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
    Compress-Archive -Path dist/ScatterLauncher -DestinationPath dist/ScatterLauncher-0.2.0-windows.zip -Force
} finally {
    Pop-Location
}
