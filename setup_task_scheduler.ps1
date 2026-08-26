# Windowsタスクスケジューラに、AIニュースまとめサイト生成の定期実行を登録する。
# GCPは使わない。このPCの電源が入っている(スリープ復帰後含む)ときにだけ実行される。
#
# 使い方: このファイルの内容を確認したうえで、PowerShellで実行してください。
#   powershell -ExecutionPolicy Bypass -File ai_news_site\setup_task_scheduler.ps1

$ErrorActionPreference = "Stop"

# --- 設定項目（必要に応じて変更） ---
$TaskName = "AiNewsSiteBuilder"
$Times = @("08:00", "18:00")  # 1日の実行時刻(24時間表記)
$ProjectDir = $PSScriptRoot
$PythonExe = "C:\Users\kodama\AppData\Local\Programs\Python\Python312\python.exe"
# --- ここまで ---

if (-not (Test-Path $PythonExe)) {
    throw "Pythonが見つかりません: $PythonExe (パスを確認してください)"
}

$RunTaskScript = Join-Path $PSScriptRoot "run_task.ps1"

# ラッパースクリプト(run_task.ps1)経由で実行する。標準出力/エラーはlogs\ai_news_run.logに残る。
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
    -Description "AI特化media MOTを自動生成する(claude ryuuプロジェクト)" `
    -Force

Write-Host "登録完了: タスク '$TaskName' が毎日 $($Times -join ', ') に実行されます。"
Write-Host "確認方法: タスクスケジューラ(taskschd.msc)を開き、タスクスケジューラライブラリから '$TaskName' を探してください。"
Write-Host "手動で今すぐ試すには: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "削除するには: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
