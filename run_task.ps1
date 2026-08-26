# タスクスケジューラから呼び出される実行ラッパー。
# build_site.pyを実行し、標準出力・エラーをlogs\ai_news_run.logに追記する。

$ProjectDir = $PSScriptRoot
$PythonExe = "C:\Users\kodama\AppData\Local\Programs\Python\Python312\python.exe"
$LogDir = Join-Path (Split-Path -Parent $ProjectDir) "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogFile = Join-Path $LogDir "ai_news_run.log"
$StdOutTmp = Join-Path $LogDir "_ai_news_stdout.tmp"
$StdErrTmp = Join-Path $LogDir "_ai_news_stderr.tmp"

Add-Content -Path $LogFile -Value "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 実行開始 ===" -Encoding UTF8

$env:PYTHONIOENCODING = "utf-8"
$proc = Start-Process -FilePath $PythonExe -ArgumentList '"build_site.py"' -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput $StdOutTmp -RedirectStandardError $StdErrTmp `
    -NoNewWindow -Wait -PassThru

Get-Content $StdOutTmp -Encoding UTF8 -ErrorAction SilentlyContinue | Add-Content -Path $LogFile -Encoding UTF8
Get-Content $StdErrTmp -Encoding UTF8 -ErrorAction SilentlyContinue | Add-Content -Path $LogFile -Encoding UTF8
Remove-Item $StdOutTmp, $StdErrTmp -ErrorAction SilentlyContinue

Add-Content -Path $LogFile -Value "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 実行終了 (終了コード: $($proc.ExitCode)) ===" -Encoding UTF8

# 生成結果をGitHubへ反映(GitHub Pagesに公開)する。変更が無い場合は何もしない。
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
Push-Location $ProjectDir
try {
    $changes = git status --porcelain
    if ($changes) {
        git add -A
        git commit -m "自動更新: $(Get-Date -Format 'yyyy-MM-dd HH:mm')" | Out-String | Add-Content -Path $LogFile -Encoding UTF8
        git push 2>&1 | Out-String | Add-Content -Path $LogFile -Encoding UTF8
        Add-Content -Path $LogFile -Value "GitHubへの反映完了" -Encoding UTF8
    } else {
        Add-Content -Path $LogFile -Value "変更なし(GitHubへの反映スキップ)" -Encoding UTF8
    }
} finally {
    Pop-Location
}
