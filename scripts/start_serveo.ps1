$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$run = Join-Path $root "data\run"
$logs = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force -Path $run, $logs | Out-Null

$ssh = Join-Path $env:SystemRoot "System32\OpenSSH\ssh.exe"
if (-not (Test-Path $ssh)) {
    $ssh = "ssh.exe"
}

$pidFile = Join-Path $run "tunnel.pid"
if (Test-Path $pidFile) {
    $old = Get-Content $pidFile | Select-Object -First 1
    if ($old) {
        Stop-Process -Id $old -Force -ErrorAction SilentlyContinue
    }
}

$outLog = Join-Path $logs "serveo.out.log"
$errLog = Join-Path $logs "serveo.err.log"
Remove-Item $outLog, $errLog -ErrorAction SilentlyContinue

$proc = Start-Process -FilePath $ssh `
    -ArgumentList "-T", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", `
        "-o", "ServerAliveInterval=30", "-o", "ExitOnForwardFailure=yes", `
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", `
        "-R", "80:localhost:8000", "serveo.net" `
    -WorkingDirectory $root -RedirectStandardOutput $outLog -RedirectStandardError $errLog `
    -PassThru -WindowStyle Hidden
$proc.Id | Set-Content $pidFile

$url = $null
for ($i = 0; $i -lt 120; $i++) {
    $content = ""
    if (Test-Path $outLog) { $content += [string](Get-Content $outLog -Raw -ErrorAction SilentlyContinue) }
    if (Test-Path $errLog) { $content += [string](Get-Content $errLog -Raw -ErrorAction SilentlyContinue) }
    if ($content) {
        $match = [regex]::Match($content, "https://[a-zA-Z0-9-]+\.serveousercontent\.com")
        if ($match.Success) {
            $url = $match.Value
            break
        }
    }
    Start-Sleep -Milliseconds 500
}

if (-not $url) {
    throw "未能获取 Serveo 地址，请查看 data\logs\serveo.err.log"
}

$url | Set-Content (Join-Path $root "data\public_url.txt")
Write-Host ""
Write-Host "Serveo 公网地址: $url" -ForegroundColor Green
Write-Host "微信回调 URL: $url/wechat"
Write-Host "CalDAV 地址:  $url/radicale/"
Write-Host ""
Write-Host "注意：Serveo 免费隧道在电脑睡眠/断网后会断开，地址会变。"
Write-Host "地址变化后需要在微信测试号后台重新提交，并更新手机 DAVx5 账户。"
