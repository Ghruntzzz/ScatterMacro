$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root 'dist\ScatterLauncher\ScatterLauncher.exe'
$previousPlatform = $env:QT_QPA_PLATFORM
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    foreach ($screen in @('launcher')) {
        $preview = Join-Path $root ('dist\smoke-' + $screen + '.png')
        if (Test-Path -LiteralPath $preview) { Remove-Item -LiteralPath $preview }
        $arguments = '--render-preview "' + $preview + '"'
        if ($screen -eq 'dashboard') {
            $arguments += ' --dashboard --config "' + (Join-Path $root 'dist\test-settings\dashboard_config.ini') + '"'
        }
        $process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru
        if (!$process.WaitForExit(20000)) {
            Stop-Process -Id $process.Id
            throw "$screen packaged startup timed out"
        }
        if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $preview)) {
            throw "$screen packaged startup failed"
        }
        Write-Output "$screen packaged startup passed"
    }
} finally {
    $env:QT_QPA_PLATFORM = $previousPlatform
}
