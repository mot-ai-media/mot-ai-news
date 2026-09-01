"""TikTok Content Posting APIの認証(OAuth)を行い、アクセストークンを.envに保存する。

サーバーを持たない静的サイト構成のため、Redirect URIには
docs/tiktok-callback.html(コードを画面に表示するだけのページ)を使う。
そこに表示されたcodeをこのスクリプトに手動で貼り付けてトークン交換する。

使い方:
  python social_tiktok_auth.py           -> 認証URLを表示
  python social_tiktok_auth.py <code>    -> codeをトークンに交換して.envに保存
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent.parent / ".env"
REDIRECT_URI = "https://mot-ai-media.github.io/mot-ai-news/tiktok-callback.html"
SCOPES = "user.info.basic,video.publish,video.upload"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def _update_env(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    keys_done = set()
    for i, line in enumerate(lines):
        for key, value in updates.items():
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                keys_done.add(key)
    for key, value in updates.items():
        if key not in keys_done:
            lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_auth_url() -> None:
    load_dotenv(ENV_PATH)
    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    if not client_key:
        print("エラー: .envにTIKTOK_CLIENT_KEYがありません。先に設定してください。")
        return
    params = {
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": "mot_auth",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print("以下のURLをブラウザで開いて、あなたのTikTokアカウントで許可してください:")
    print(url)
    print("\n許可すると tiktok-callback.html にcodeが表示されるので、それをコピーして")
    print("python social_tiktok_auth.py <code> を実行してください。")


def exchange_code(code: str) -> None:
    load_dotenv(ENV_PATH)
    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    if not client_key or not client_secret:
        print("エラー: .envにTIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRETがありません。")
        return

    data = urllib.parse.urlencode({
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"エラー({e.code}): {e.read().decode('utf-8', errors='replace')}")
        return

    if "access_token" not in result:
        print("トークン取得失敗:", result)
        return

    _update_env({
        "TIKTOK_ACCESS_TOKEN": result["access_token"],
        "TIKTOK_REFRESH_TOKEN": result.get("refresh_token", ""),
        "TIKTOK_OPEN_ID": result.get("open_id", ""),
    })
    print("成功: アクセストークンを.envに保存しました。")
    print(f"有効期限: {result.get('expires_in')}秒 (約{result.get('expires_in', 0) // 3600}時間)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_auth_url()
    else:
        exchange_code(sys.argv[1])
