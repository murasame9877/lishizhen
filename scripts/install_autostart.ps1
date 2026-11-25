# 登录 Windows 后自动拉起后端 watchdog 与桥接 supervisor。
# 用法：右键“使用 PowerShell 运行”，或在 PowerShell 中执行本文件。
# 若提示权限不足，请用管理员 PowerShell 再执行一次。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$tasks = @(
    @{
        Name = "SDG-Demo-App"
        Script = Join-Path $root "scripts\run_app.ps1"
        Desc = "SDG demo: FastAPI + Radicale watchdog"
    },
    @{
        Name = "SDG-Demo-Bridge"
        Script = Join-Path $root "scripts\run_bridge.ps1"
        Desc = "SDG demo: WeCom KF web bridge supervisor"
    }
)

foreach ($task in $tasks) {
    $action = New-ScheduledTaskAction -Execute $powershell `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$($task.Script)`"" `
        -WorkingDirectory $root
    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $trigger `
        -Principal $principal -Description $task.Desc -Force | Out-Null
    Write-Host "[OK] 已注册计划任务 $($task.Name)"
}

Write-Host ""
Write-Host "下次登录 Windows 会自动启动。现在可手动启动："
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\run_app.ps1`""
Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\run_bridge.ps1`""
Write-Host ""
Write-Host "取消自启动："
Write-Host "  Unregister-ScheduledTask -TaskName SDG-Demo-App -Confirm:`$false"
Write-Host "  Unregister-ScheduledTask -TaskName SDG-Demo-Bridge -Confirm:`$false"
