$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$script:failCount = 0

function Check($name, [bool]$ok, $detail) {
    if ($ok) {
        Write-Host ("[OK]   {0,-22} {1}" -f $name, $detail)
    } else {
        Write-Host ("[FAIL] {0,-22} {1}" -f $name, $detail)
        $script:failCount++
    }
}

Write-Host "=== 演示预检 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="

# 1. 后端
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/healthz" -TimeoutSec 4
    Check "backend" ([bool]$health.ok) $health.time
} catch {
    Check "backend" $false $_.Exception.Message
}

# 2. 桥接进程
$bridgePid = Get-Content "data\run\bridge.pid" -ErrorAction SilentlyContinue
$proc = if ($bridgePid) { Get-Process -Id $bridgePid -ErrorAction SilentlyContinue } else { $null }
Check "bridge-process" ($null -ne $proc) "pid=$bridgePid"

# 3. 桥接心跳（日志 3 分钟内有更新）
$log = Get-Item "data\logs\bridge.out.log" -ErrorAction SilentlyContinue
if ($log) {
    $age = ((Get-Date) - $log.LastWriteTime).TotalSeconds
    Check "bridge-heartbeat" ($age -lt 180) ("last-write {0:N0}s ago" -f $age)
} else {
    Check "bridge-heartbeat" $false "bridge.out.log missing"
}

# 4. 工作台登录状态
$statusPath = "data\run\bridge_status.json"
if (Test-Path $statusPath) {
    try {
        $status = Get-Content $statusPath -Raw -ErrorAction Stop | ConvertFrom-Json
        Check "workbench-login" ($status.state -eq "running") ("state={0} updated={1}" -f $status.state, $status.updated_at)
    } catch {
        Check "workbench-login" $false "status file unreadable"
    }
} else {
    Check "workbench-login" $false "bridge_status.json missing (restart bridge)"
}

# 5. 手机与隧道
$adb = Join-Path $root "tools\platform-tools-dl\platform-tools\adb.exe"
if (Test-Path $adb) {
    $devices = & $adb devices 2>$null
    $deviceOk = @($devices | Where-Object { $_ -match "\sdevice\s*$" }).Count -gt 0
    Check "phone-usb" $deviceOk (($devices -join "; ").Trim())

    $reverse = & $adb reverse --list 2>$null
    $reverseOk = ($reverse -join "`n") -match "tcp:8000"
    Check "adb-reverse" $reverseOk (($reverse -join "; ").Trim())

    $cal = & $adb shell content query --uri content://com.android.calendar/calendars --projection _id:account_name:account_type:calendar_displayName 2>$null
    $calRow = $cal | Select-String "account_type=bitfire.at.davdroid" | Select-Object -First 1
    Check "davx5-calendar" ($null -ne $calRow) "sdg/calendar"

    if ($calRow -and ($calRow.ToString() -match "_id=(\d+)")) {
        $calId = $matches[1]
        $events = & $adb shell content query --uri content://com.android.calendar/events --projection _id:title --where "calendar_id=$calId" 2>$null
        $eventCount = @($events | Select-String "Row:").Count
        Check "calendar-events" ($eventCount -gt 0) "calendar_id=$calId, $eventCount rows"
    } else {
        Check "calendar-events" $false "DAVx5 calendar id not found"
    }
} else {
    Check "adb" $false "adb.exe missing"
}

# 6. 磁盘
$driveName = (Get-Item $root).PSDrive.Name
$freeGB = (Get-PSDrive $driveName).Free / 1GB
Check "disk-space" ($freeGB -gt 2) ("{0:N1} GB free on {1}:" -f $freeGB, $driveName)

Write-Host ""
if ($script:failCount -eq 0) {
    Write-Host "== GO：可以开始演示 ==" -ForegroundColor Green
    exit 0
} else {
    Write-Host ("== NO-GO：{0} 项未通过 ==" -f $script:failCount) -ForegroundColor Red
    exit 1
}
