$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venv = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "data\logs"
$run = Join-Path $root "data\run"
New-Item -ItemType Directory -Force -Path $logs, $run | Out-Null

$PID | Set-Content (Join-Path $run "bridge_watchdog.pid")

$out = Join-Path $logs "bridge.out.log"
$err = Join-Path $logs "bridge.err.log"
$supervisor = Join-Path $logs "bridge.supervisor.log"

while ($true) {
    if (Test-Path $out) {
        Move-Item $out (Join-Path $logs "bridge.out.prev.log") -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $err) {
        Move-Item $err (Join-Path $logs "bridge.err.prev.log") -Force -ErrorAction SilentlyContinue
    }

    $proc = Start-Process -FilePath $venv `
        -ArgumentList "-u", "bot/kf_web_bridge.py" `
        -WorkingDirectory $root -RedirectStandardOutput $out -RedirectStandardError $err `
        -PassThru -WindowStyle Hidden

    $proc.Id | Set-Content (Join-Path $run "bridge.pid")
    Add-Content -Path $supervisor -Value "$(Get-Date -Format o) started pid=$($proc.Id)"

    $proc.WaitForExit()
    Add-Content -Path $supervisor -Value "$(Get-Date -Format o) exited code=$($proc.ExitCode)"
    Start-Sleep -Seconds 3
}
