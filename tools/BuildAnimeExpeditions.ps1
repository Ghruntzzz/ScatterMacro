$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
Push-Location $root
try {
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed --name AnimeExpeditions --icon assets/scattermacro.ico --collect-all rapidocr --collect-all onnxruntime --add-data 'assets;assets' anime_main.py
    if ($LASTEXITCODE -ne 0) { throw 'Macro build failed' }
    $qt = & $python -c "import pathlib, PySide6; print(pathlib.Path(PySide6.__file__).parent)"
    foreach ($dll in Get-ChildItem -LiteralPath $qt -File | Where-Object { $_.Name -match '^(msvcp140|vcruntime140).*\.dll$' }) {
        Copy-Item -LiteralPath $dll.FullName -Destination (Join-Path $root ('dist\AnimeExpeditions\_internal\' + $dll.Name)) -Force
    }
    $icu = Join-Path $root 'dist\AnimeExpeditions\_internal\icuuc.dll'
    if (Test-Path -LiteralPath $icu) { Remove-Item -LiteralPath $icu }
    $env:QT_QPA_PLATFORM = 'offscreen'
    $arguments = '--config-dir "' + (Join-Path $root 'dist\macro-smoke-config') + '" --render-preview "' + (Join-Path $root 'dist\macro-smoke.png') + '"'
    $process = Start-Process -FilePath (Join-Path $root 'dist\AnimeExpeditions\AnimeExpeditions.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru
    if (!$process.WaitForExit(20000)) { Stop-Process -Id $process.Id; throw 'Macro startup timed out' }
    if ($process.ExitCode -ne 0 -or !(Test-Path 'dist\macro-smoke.png')) { throw 'Macro startup failed' }
    & $python tools/PackageMacro.py
    if ($LASTEXITCODE -ne 0) { throw 'Macro package validation failed' }
} finally {
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    Pop-Location
}
