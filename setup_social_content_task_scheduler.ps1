# Windowsタスクスケジューラに、SNS下書き自動生成の定期実行を登録する。
# MotSocialAutoPost(07:00/11:00/19:00に投稿)の直前、各30分前に実行し、
# 投稿するものが無くてスキップされ続ける事故を防ぐ。
$ErrorActionPreference = "Stop"

$TaskName = "MotSocialContentGen"
$Times = @("06:30", "10:30", "18:30")
$ProjectDir = $PSScriptRoot
$PythonExe = "C:\Users\kodama\AppData\Local\Programs\Python\Python312\python.exe"

if (-not (Test-Path $PythonExe)) { throw "Pythonが見つかりません: $PythonExe" }

$RunTaskScript = Join-Path $PSScriptRoot "run_social_content.ps1"
$psArgument = '-NoProfile -ExecutionPolicy Bypass -File "' + $RunTaskScript + '"'
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgument -WorkingDirectory $ProjectDir

$triggers = $Times | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings `
    -Description "SNS投稿下書きを自動生成する(claude ryuuプロジェクト)" -Force

Write-Host "Registered: $TaskName will run daily at $($Times -join ', ')"
