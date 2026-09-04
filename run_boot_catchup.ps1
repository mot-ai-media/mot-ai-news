# PC起動時(ログオン時)に呼ばれる。オフだった間に飛んだ自動実行を追いつかせる。
# 3つの処理を同時ではなく順番に実行する(同時に走ってgitがぶつかり全滅した事故の再発防止)。

$ProjectDir = $PSScriptRoot
$PythonExe = "C:\Users\kodama\AppData\Local\Programs\Python\Python312\python.exe"
$LogDir = Join-Path (Split-Path -Parent $ProjectDir) "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "boot_catchup.log"

Add-Content -Path $LogFile -Value "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 起動時キャッチアップ開始 ===" -Encoding UTF8

# PCが起動しきる前の不安定なタイミングを避けるため、少し待ってから始める
Start-Sleep -Seconds 30

Push-Location $ProjectDir
try {
    Add-Content -Path $LogFile -Value "--- ニュース記事更新 ---" -Encoding UTF8
    & $PythonExe "build_site.py" 2>&1 | Add-Content -Path $LogFile -Encoding UTF8
    git add -A 2>&1 | Out-Null
    if (git status --porcelain) {
        git commit -m "自動更新: $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>&1 | Add-Content -Path $LogFile -Encoding UTF8
        git push 2>&1 | Add-Content -Path $LogFile -Encoding UTF8
    }

    Start-Sleep -Seconds 15

    Add-Content -Path $LogFile -Value "--- SNS自動投稿 ---" -Encoding UTF8
    & $PythonExe "social_auto_post.py" 2>&1 | Add-Content -Path $LogFile -Encoding UTF8

    Start-Sleep -Seconds 10

    Add-Content -Path $LogFile -Value "--- 分析ログ記録 ---" -Encoding UTF8
    & $PythonExe "social_analytics_log.py" 2>&1 | Add-Content -Path $LogFile -Encoding UTF8
} finally {
    Pop-Location
}

Add-Content -Path $LogFile -Value "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 起動時キャッチアップ終了 ===" -Encoding UTF8
