# Windowsタスクスケジューラに、Claude Fable/ChatGPT Atlas専用ウォッチの定期実行を登録する。
# 2時間おきに実行し、新しい実記事が見つかったときだけ確認なしでサイトを更新する。
#
# 使い方: このファイルの内容を確認したうえで、PowerShellで実行してください。
#   powershell -ExecutionPolicy Bypass -File ai_news_site\setup_fable_atlas_task_scheduler.ps1

$ErrorActionPreference = "Stop"

# --- 設定項目(必要に応じて変更) ---
$TaskName = "MotFableAtlasWatch"
$ProjectDir = $PSScriptRoot
$PythonExe = "C:\Users\kodama\AppData\Local\Programs\Python\Python312\python.exe"
# --- ここまで ---

if (-not (Test-Path $PythonExe)) {
    throw "Pythonが見つかりません: $PythonExe (パスを確認してください)"
}

$RunTaskScript = Join-Path $PSScriptRoot "run_fable_atlas.ps1"

$psArgument = '-NoProfile -ExecutionPolicy Bypass -File "' + $RunTaskScript + '"'
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgument -WorkingDirectory $ProjectDir

# 今すぐ(次の分)を起点に、2時間おきに無期限で繰り返す
$startTime = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startTime `
    -RepetitionInterval (New-TimeSpan -Hours 2) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Claude Fable / ChatGPT Atlas関連ニュースを2時間おきに探して自動更新する(claude ryuuプロジェクト)" `
    -Force

Write-Host "登録完了: タスク '$TaskName' が2時間おきに実行されます(起点: $startTime)。"
Write-Host "確認方法: タスクスケジューラ(taskschd.msc)を開き、タスクスケジューラライブラリから '$TaskName' を探してください。"
Write-Host "手動で今すぐ試すには: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "削除するには: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
