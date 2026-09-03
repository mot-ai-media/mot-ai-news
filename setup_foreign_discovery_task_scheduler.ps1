# Windowsタスクスケジューラに、海外Tier1/2ニュース発見の定期実行を登録する(3時間おき)。
$ErrorActionPreference = "Stop"

$TaskName = "MotForeignDiscovery"
$ProjectDir = $PSScriptRoot
$PythonExe = "C:\Users\kodama\AppData\Local\Programs\Python\Python312\python.exe"

if (-not (Test-Path $PythonExe)) { throw "Pythonが見つかりません: $PythonExe" }

$RunTaskScript = Join-Path $PSScriptRoot "run_foreign_discovery.ps1"
$psArgument = '-NoProfile -ExecutionPolicy Bypass -File "' + $RunTaskScript + '"'
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgument -WorkingDirectory $ProjectDir

$startTime = (Get-Date).AddMinutes(2)
$trigger = New-ScheduledTaskTrigger -Once -At $startTime `
    -RepetitionInterval (New-TimeSpan -Hours 3) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "海外Tier1/2メディアからAI関連ニュースを発見・自動公開する(claude ryuuプロジェクト)" -Force

Write-Host "Registered: $TaskName will run every 3 hours (start: $startTime)"
