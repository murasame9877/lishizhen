$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venv = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "data\logs"
$run = Join-Path $root "data\run"
New-Item -ItemType Directory -Force -Path $logs, $run | Out-Null

$PID | Set-Content (Join-Path $run "app_watchdog.pid")

$out = Join-Path $logs "app.out.log"
$err = Join-Path $logs "app.err.log"

while ($true) {
    if (Test-Path $err) {
        Copy-Item $err (Join-Path $logs "app.err.prev.log") -Force -ErrorAction SilentlyContinue
    }

    $proc = Start-Process -FilePath $venv `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" `
        -WorkingDirectory $root -RedirectStandardOutput $out -RedirectStandardError $err `
        -PassThru -WindowStyle Hidden

    $proc.Id | Set-Content (Join-Path $run "app.pid")
    $proc.WaitForExit()
    Start-Sleep -Seconds 2
}
