# 復旧手順(このPCが壊れた・買い替えた場合)

ソースコード・記事データはGitHub(`https://github.com/mottainAI0214/mot-ai-news`)に
バックアップされているが、**`.env`の秘密情報だけはどこにもバックアップされていない**(意図的。
秘密情報を平文でどこかに保存するのは危険なため)。新しいPCで再開するには以下の再設定が必要。

## 1. リポジトリを取得

```powershell
git clone https://github.com/mottainAI0214/mot-ai-news.git
cd mot-ai-news
pip install -r ../requirements.txt   # feedparser, anthropic, python-dotenv
```

## 2. `.env`を再作成(このPC以外に控えが無いので手動で再設定)

プロジェクトルート(`ai_news_site`の一つ上)に`.env`を作成し、以下を設定:

```
ANTHROPIC_API_KEY=（Anthropic Consoleで新規発行 or 既存キーを再入力）
GMAIL_ADDRESS=（既存のGmailアドレス）
GMAIL_APP_PASSWORD=（Googleアカウントで「アプリパスワード」を再発行）
GMAIL_TO=（省略可。空ならGMAIL_ADDRESS宛）
```

## 3. GitHub CLIの認証

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

## 4. Windowsタスクスケジューラに再登録

```powershell
powershell -ExecutionPolicy Bypass -File ai_news_site\setup_task_scheduler.ps1
```

## 5. 動作確認

```powershell
python ai_news_site\build_site.py
```

新規記事が生成され、`logs\ai_news_run.log`にエラーが出なければ復旧完了。

## 外部サービス側で再設定が不要なもの

- GitHub Pages: リポジトリ設定は既にGitHub側に残っている(コード再取得のみでOK)
- GoatCounter: `mottainai.goatcounter.com`のアカウント設定はGoatCounter側に残っている(このPC固有の設定ではない)
- Google Search Console: 所有権確認用タグはコードに含まれているため再pushすれば有効なまま
- A8.net: アフィリエイトコードはコードに含まれている(A8.netアカウント自体はサイトと独立)
