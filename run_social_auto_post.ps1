# タスクスケジューラから呼び出される実行ラッパー。
# social_auto_post.pyを実行し、標準出力・エラーをlogs\social_auto_post.logに追記する。

$ProjectDir = $PSScriptRoot
$PythonExe = "C:\Users\kodama\AppData\Local\Programs\Python\Python312\python.exe"
$LogDir = Join-Path (Split-Path -Parent $ProjectDir) "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogFile = Join-Path $LogDir "social_auto_post.log"
$StdOutTmp = Join-Path $LogDir "_social_auto_post_stdout.tmp"
$StdErrTmp = Join-Path $LogDir "_social_auto_post_stderr.tmp"

Add-Content -Path $LogFile -Value "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 実行開始 ===" -Encoding UTF8

$env:PYTHONIOENCODING = "utf-8"
$proc = Start-Process -FilePath $PythonExe -ArgumentList '"social_auto_post.py"' -WorkingDirectory $ProjectDir `
    -RedirectStandardOutput $StdOutTmp -RedirectStandardError $StdErrTmp `
    -NoNewWindow -Wait -PassThru

Get-Content $StdOutTmp -Encoding UTF8 -ErrorAction SilentlyContinue | Add-Content -Path $LogFile -Encoding UTF8
Get-Content $StdErrTmp -Encoding UTF8 -ErrorAction SilentlyContinue | Add-Content -Path $LogFile -Encoding UTF8
Remove-Item $StdOutTmp, $StdErrTmp -ErrorAction SilentlyContinue

Add-Content -Path $LogFile -Value "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 実行終了 (終了コード: $($proc.ExitCode)) ===" -Encoding UTF8
