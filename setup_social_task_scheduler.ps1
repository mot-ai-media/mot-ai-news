# WindowsタスクスケジューラにSNS自動投稿の定期実行を登録する。
# 1日3つの時間枠(7時/11時/19時)でsocial_auto_post.pyを呼ぶが、実際に投稿するのは
# そのうち承認済みコンテンツがある回のみ、かつ1日の上限は2回(social_auto_post.py側で判定)。
#
# 使い方: このファイルの内容を確認したうえで、PowerShellで実行してください。
#   powershell -ExecutionPolicy Bypass -File ai_news_site\setup_social_task_scheduler.ps1

$ErrorActionPreference = "Stop"

# --- 設定項目（必要に応じて変更） ---
$TaskName = "MotSocialAutoPost"
$Times = @("07:00", "11:00", "19:00")  # 1日の実行時刻(24時間表記)
$ProjectDir = $PSScriptRoot
$PythonExe = "C:\Users\kodama\AppData\Local\Programs\Python\Python312\python.exe"
# --- ここまで ---

if (-not (Test-Path $PythonExe)) {
    throw "Pythonが見つかりません: $PythonExe (パスを確認してください)"
}

$RunTaskScript = Join-Path $PSScriptRoot "run_social_auto_post.ps1"

$psArgument = '-NoProfile -ExecutionPolicy Bypass -File "' + $RunTaskScript + '"'
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgument -WorkingDirectory $ProjectDir

$triggers = $Times | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Description "MOTのInstagram自動投稿(承認済みコンテンツがあるときのみ、1日最大2回)" `
    -Force

Write-Host "登録完了: タスク '$TaskName' が毎日 $($Times -join ', ') にチェックされ、承認済みコンテンツがあれば投稿されます(1日最大2回)。"
Write-Host "確認方法: タスクスケジューラ(taskschd.msc)を開き、タスクスケジューラライブラリから '$TaskName' を探してください。"
Write-Host "手動で今すぐ試すには: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "削除するには: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
