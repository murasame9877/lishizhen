param([switch]$Quiet)

$root = Split-Path -Parent $PSScriptRoot
$run = Join-Path $root "data\run"

foreach ($name in @("app_watchdog", "app", "tunnel")) {
    $pidFile = Join-Path $run "$name.pid"
    if (Test-Path $pidFile) {
        $processId = Get-Content $pidFile | Select-Object -First 1
        if ($processId) {
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($process) {
                Stop-Process -Id $processId -Force
            }
        }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
}

if (-not $Quiet) {
    Write-Host "已停止应用与隧道"
}
