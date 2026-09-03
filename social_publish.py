"""social_queue.jsonで承認済み(status=="approved")の記事を、実際にInstagramへ投稿する。

安全のためのルール:
- statusが"approved"の記事しか対象にしない(承認はsocial_review.htmlで確認したうえで、
  social_queue.json側の status を手動で書き換える既存の運用を踏襲)
- dry_run(デフォルト)では画像の存在確認までしか行わず、実際のアップロード・投稿は一切しない。
  実際に投稿するときだけ明示的に --live を付けて実行する。
- トークン等の秘密情報は標準出力に出さない。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).parent
SOCIAL_QUEUE_PATH = BASE_DIR / "social_queue.json"
ASSETS_DIR = BASE_DIR / "social_assets"
DOCS_SOCIAL_DIR = BASE_DIR / "docs" / "social"
SITE_BASE_URL = "https://mot-ai-media.github.io/mot-ai-news"

GRAPH_API = "https://graph.instagram.com/v21.0"
SLIDE_ORDER_SUFFIXES = ["hook", "slide2", "slide3", "cta"]


class PublishError(Exception):
    pass


def _api_call(method: str, url: str, params: dict) -> dict:
    """Graph APIへのGET/POSTを行う。エラー時はトークンを含まない安全なメッセージだけ出す。"""
    data = urllib.parse.urlencode(params).encode("utf-8")
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}", method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except json.JSONDecodeError:
            msg = body
        raise PublishError(f"Graph API エラー({e.code}): {msg}") from None


def _load_credentials() -> tuple[str, str]:
    load_dotenv(BASE_DIR.parent / ".env")
    token = os.environ.get("INSTAGRAM_LONG_LIVED_TOKEN")
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    if not token or not ig_user_id:
        raise PublishError("INSTAGRAM_LONG_LIVED_TOKEN または INSTAGRAM_USER_ID が .env にありません")
    return token, ig_user_id


def collect_slide_files(slug: str, angle: str) -> list[Path]:
    files = [ASSETS_DIR / f"{slug}_{angle}_{suf}.png" for suf in SLIDE_ORDER_SUFFIXES]
    files = [f for f in files if f.exists()]
    if not files:
        raise PublishError(f"{slug}/{angle} の画像が social_assets/ に見つかりません")
    return files


def publish_images_to_pages(slug: str, angle: str, files: list[Path]) -> list[str]:
    """画像をdocs/social/にコピーし、GitHubへpushして公開URLにする。

    公開のたびにタイムスタンプ付きのフォルダに置き、URLを必ず新規にする。
    同じ記事を削除→再投稿する際に同じURLを使い回すと、GitHub PagesのCDNや
    Instagram側の画像キャッシュが古い中身を返し続け、差し替えた新しい画像が
    反映されない事故が実際に起きたため(URLが同じ=中身も同じという前提でキャッシュされる)。"""
    version = datetime.now().strftime("%Y%m%d%H%M%S")
    target_dir = DOCS_SOCIAL_DIR / slug / f"{angle}_{version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    urls = []
    for f in files:
        shutil.copy2(f, target_dir / f.name)
        urls.append(f"{SITE_BASE_URL}/social/{slug}/{angle}_{version}/{f.name}")

    subprocess.run(["git", "add", str(target_dir)], cwd=BASE_DIR, check=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=BASE_DIR)
    if result.returncode != 0:
        subprocess.run(
            ["git", "commit", "-m", f"SNS投稿用画像を追加: {slug}/{angle}"],
            cwd=BASE_DIR, check=True,
        )
        subprocess.run(["git", "push"], cwd=BASE_DIR, check=True)
        print("GitHub Pagesへpush完了。反映まで数十秒〜数分待つ必要あり。")
    return urls


def _wait_urls_live(urls: list[str], timeout: int = 180) -> None:
    """GitHub Pagesのビルドには数十秒〜数分かかることがあるため、
    固定秒数待つのではなく、画像が実際に200で開けるまでポーリングする。"""
    start = time.time()
    for url in urls:
        while True:
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        break
            except urllib.error.HTTPError:
                pass
            except urllib.error.URLError:
                pass
            if time.time() - start > timeout:
                raise PublishError(f"GitHub Pagesの反映待ちがタイムアウトしました: {url}")
            time.sleep(5)


def _wait_container_ready(container_id: str, token: str, timeout: int = 90) -> None:
    start = time.time()
    while time.time() - start < timeout:
        result = _api_call("GET", f"{GRAPH_API}/{container_id}", {
            "fields": "status_code",
            "access_token": token,
        })
        status = result.get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise PublishError(f"画像コンテナの処理に失敗しました: {container_id}")
        time.sleep(3)
    raise PublishError(f"画像コンテナの処理がタイムアウトしました: {container_id}")


def create_carousel_item(image_url: str, ig_user_id: str, token: str) -> str:
    result = _api_call("POST", f"{GRAPH_API}/{ig_user_id}/media", {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": token,
    })
    return result["id"]


def create_carousel_container(child_ids: list[str], caption: str, ig_user_id: str, token: str) -> str:
    result = _api_call("POST", f"{GRAPH_API}/{ig_user_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "caption": caption,
        "access_token": token,
    })
    return result["id"]


def publish_container(container_id: str, ig_user_id: str, token: str) -> str:
    result = _api_call("POST", f"{GRAPH_API}/{ig_user_id}/media_publish", {
        "creation_id": container_id,
        "access_token": token,
    })
    return result["id"]


TIKTOK_MANUAL_DIR = BASE_DIR / "tiktok_manual_post"


def _save_for_manual_tiktok(slug: str, angle: str, files: list[Path], angle_data: dict) -> None:
    """TikTok自動投稿は諦め、Instagramに投稿した画像+キャプションを手動投稿用フォルダに
    コピーしておく(スマホでこのフォルダを見て、TikTokアプリから手動でアップロードする運用)。"""
    dest_dir = TIKTOK_MANUAL_DIR / f"{slug}_{angle}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, dest_dir / f.name)
    caption = angle_data.get("caption_tiktok") or angle_data.get("caption_instagram", "")
    (dest_dir / "caption.txt").write_text(caption, encoding="utf-8")
    print(f"TikTok手動投稿用に保存しました: {dest_dir}")

    import _gen_tiktok_queue
    _gen_tiktok_queue.build()


def publish_to_instagram(slug: str, angle: str, live: bool = False) -> dict:
    queue = json.loads(SOCIAL_QUEUE_PATH.read_text(encoding="utf-8"))
    item = queue.get(slug)
    if not item:
        raise PublishError(f"{slug} がキューに見つかりません")
    if item.get("status") != "approved":
        raise PublishError(
            f"status が 'approved' ではありません(現在: '{item.get('status')}')。"
            " social_review.html で内容を確認し、social_queue.json の status を"
            " 'approved' に書き換えてから実行してください。"
        )
    angle_data = next((a for a in item["angles"] if a["type"] == angle), None)
    if angle_data is None:
        raise PublishError(f"angle '{angle}' が見つかりません")

    # 投稿の直前に必ず画像を再生成する(social_assets/の既存ファイルを信用しない)。
    # 過去に「記事生成時に作った古い画像がキューに残ったまま、画像パイプライン側だけ
    # 直しても反映されず投稿されてしまう」事故が実際に起きたため、鮮度を保証する。
    import social_visuals as sv
    tags = item.get("tags", [])
    image_url = item.get("image_url")
    sv.make_hook_slide(tags, angle_data["hook"], angle, slug, "", image_url)
    sv.make_carousel_slides(angle_data["carousel"], angle, slug, tags, "", image_url)
    sv.make_cta_slide(slug, angle_data.get("cta"), angle)

    files = collect_slide_files(slug, angle)
    print(f"[{slug}/{angle}] 画像{len(files)}枚を再生成して確認しました: {[f.name for f in files]}")

    if not live:
        print("(dry run: 実際の投稿は行いません。実行するときは --live を付けてください)")
        return {"live": False, "files": [f.name for f in files]}

    token, ig_user_id = _load_credentials()

    urls = publish_images_to_pages(slug, angle, files)
    print("公開URL:")
    for u in urls:
        print(f"  {u}")
    print("画像がGitHub Pagesで実際に開けるようになるまで待機します...")
    _wait_urls_live(urls)
    print("画像の反映を確認しました。投稿処理に進みます。")

    child_ids = []
    for url in urls:
        cid = create_carousel_item(url, ig_user_id, token)
        _wait_container_ready(cid, token)
        child_ids.append(cid)
        print(f"  画像コンテナ作成完了 ({len(child_ids)}/{len(urls)})")

    caption = angle_data.get("caption_instagram", "")
    parent_id = create_carousel_container(child_ids, caption, ig_user_id, token)
    _wait_container_ready(parent_id, token)
    print("カルーセル本体コンテナ作成完了。公開します...")

    media_id = publish_container(parent_id, ig_user_id, token)
    print(f"投稿完了。media_id: {media_id}")

    _save_for_manual_tiktok(slug, angle, files, angle_data)

    item["status"] = "published"
    item["published_angle"] = angle
    item["published_media_id"] = media_id
    item["published_at"] = datetime.now().isoformat(timespec="seconds")
    queue[slug] = item
    SOCIAL_QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"live": True, "media_id": media_id, "urls": urls}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使い方: python social_publish.py <slug> <angle> [--live]")
        sys.exit(1)
    try:
        res = publish_to_instagram(sys.argv[1], sys.argv[2], live="--live" in sys.argv)
        print(res)
    except PublishError as e:
        print(f"エラー: {e}")
        sys.exit(1)
