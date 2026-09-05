# タスクスケジューラから呼び出される実行ラッパー(SNS下書き生成、1日3回)。
# social_content.pyを実行し、新しい記事からInstagram投稿の下書きをキューに追加する。
# ここが動いていないと social_auto_post.py は「投稿するものが無い」と毎回スキップし続ける。

$ProjectDir = $PSScriptRoot
$PythonExe = "C:\Users\kodama\AppData\Local\Programs\Python\Python312\python.exe"
$LogDir = Join-Path (Split-Path -Parent $ProjectDir) "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogFile = Join-Path $LogDir "social_content_run.log"
$StdOutTmp = Join-Path $LogDir "_social_content_stdout.tmp"
$StdErrTmp = Join-Path $LogDir "_social_content_stderr.tmp"

Add-Content -Path $LogFile -Value "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 実行開始 ===" -Encoding UTF8

$env:PYTHONIOENCODING = "utf-8"
$proc = Start-Process -FilePath $PythonExe -ArgumentList '"social_content.py"' -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput $StdOutTmp -RedirectStandardError $StdErrTmp `
    -NoNewWindow -Wait -PassThru

Get-Content $StdOutTmp -Encoding UTF8 -ErrorAction SilentlyContinue | Add-Content -Path $LogFile -Encoding UTF8
Get-Content $StdErrTmp -Encoding UTF8 -ErrorAction SilentlyContinue | Add-Content -Path $LogFile -Encoding UTF8
Remove-Item $StdOutTmp, $StdErrTmp -ErrorAction SilentlyContinue

Add-Content -Path $LogFile -Value "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 実行終了 (終了コード: $($proc.ExitCode)) ===" -Encoding UTF8

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
Push-Location $ProjectDir
try {
    $changes = git status --porcelain
    if ($changes) {
        git add -A
        git commit -m "SNS下書き自動生成: $(Get-Date -Format 'yyyy-MM-dd HH:mm')" | Out-String | Add-Content -Path $LogFile -Encoding UTF8
        git push 2>&1 | Out-String | Add-Content -Path $LogFile -Encoding UTF8
        Add-Content -Path $LogFile -Value "GitHubへの反映完了" -Encoding UTF8
    } else {
        Add-Content -Path $LogFile -Value "変更なし(GitHubへの反映スキップ)" -Encoding UTF8
    }
} finally {
    Pop-Location
}
