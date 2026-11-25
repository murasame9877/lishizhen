$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venv = Join-Path $root ".venv\Scripts\python.exe"
$tunnelExe = Join-Path $root "tools\cloudflared.exe"
$data = Join-Path $root "data"
$logs = Join-Path $data "logs"
$run = Join-Path $data "run"

New-Item -ItemType Directory -Force -Path $logs, $run | Out-Null

if (-not (Test-Path $venv)) {
    throw "缺少 .venv，请先执行: python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt"
}
if (-not (Test-Path $tunnelExe)) {
    throw "缺少 tools\cloudflared.exe"
}

& (Join-Path $PSScriptRoot "stop_all.ps1") -Quiet

$watchdog = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "run_app.ps1") `
    -WorkingDirectory $root -PassThru -WindowStyle Hidden
$watchdog.Id | Set-Content (Join-Path $run "app_watchdog.pid")

$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/healthz" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $ok = $true
            break
        }
    } catch {
    }
    Start-Sleep -Milliseconds 500
}
if (-not $ok) {
    throw "应用未启动，请查看 data\logs\app.err.log"
}

$tunOut = Join-Path $logs "tunnel.out.log"
$tunErr = Join-Path $logs "tunnel.err.log"
Remove-Item $tunOut, $tunErr -ErrorAction SilentlyContinue
$tun = Start-Process -FilePath $tunnelExe `
    -ArgumentList "tunnel", "--url", "http://127.0.0.1:8000", "--protocol", "http2", "--no-autoupdate" `
    -WorkingDirectory $root -RedirectStandardOutput $tunOut -RedirectStandardError $tunErr `
    -PassThru -WindowStyle Hidden
$tun.Id | Set-Content (Join-Path $run "tunnel.pid")

$url = $null
for ($i = 0; $i -lt 120; $i++) {
    $content = ""
    if (Test-Path $tunErr) {
        $content += [string](Get-Content $tunErr -Raw -ErrorAction SilentlyContinue)
    }
    if (Test-Path $tunOut) {
        $content += [string](Get-Content $tunOut -Raw -ErrorAction SilentlyContinue)
    }
    if ($content) {
        $match = [regex]::Match($content, "https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        if ($match.Success) {
            $url = $match.Value
            break
        }
    }
    Start-Sleep -Milliseconds 500
}
if (-not $url) {
    Write-Warning "Cloudflare 快速隧道创建失败（常见原因：429 限流），改用 Serveo 免费隧道。"
    & (Join-Path $PSScriptRoot "start_serveo.ps1")
    exit 0
}

$url | Set-Content (Join-Path $data "public_url.txt")

Write-Host ""
Write-Host "公网地址: $url" -ForegroundColor Green
Write-Host "微信回调 URL: $url/wechat"
Write-Host "CalDAV 地址:  $url/radicale/"
Write-Host ""
Write-Host "下一步："
Write-Host "1. 打开公众平台测试号 -> 接口配置信息"
Write-Host "2. URL 填 $url/wechat"
Write-Host "3. Token 填 .env 里的 WECHAT_TOKEN"
Write-Host "4. 点提交，然后用手机微信扫码关注测试号"
Write-Host ""
Write-Host "停止服务: scripts\stop_all.ps1"
