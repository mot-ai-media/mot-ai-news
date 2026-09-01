"""social_queue.jsonで承認済みの記事を、TikTokへ「フォト投稿」として公開する。

TikTokの投稿にはPHOTO(複数画像のスライド投稿)モードがあり、Instagramのカルーセルと
同じ生成済み画像(social_publish.pyがdocs/social/に公開したもの)をそのまま再利用する。
動画生成は行わない(既存方針を踏襲)。

安全のためのルール:
- statusが"approved"の記事しか対象にしない
- 審査が通るまではTikTok側の仕様でどのみち非公開(自分にしか見えない)扱いになる
- --liveを付けない限り実際には投稿しない(ドライラン)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
import os

from social_publish import PublishError, collect_slide_files, publish_images_to_pages

BASE_DIR = Path(__file__).parent
SOCIAL_QUEUE_PATH = BASE_DIR / "social_queue.json"
API_BASE = "https://open.tiktokapis.com/v2"


def _api_call(endpoint: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{API_BASE}{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise PublishError(f"TikTok APIエラー({e.code}): {body}") from None


def publish_to_tiktok(slug: str, angle: str, live: bool = False) -> dict:
    load_dotenv(BASE_DIR.parent / ".env")
    queue = json.loads(SOCIAL_QUEUE_PATH.read_text(encoding="utf-8"))
    item = queue.get(slug)
    if not item:
        raise PublishError(f"{slug} がキューに見つかりません")
    if item.get("status") != "approved":
        raise PublishError(f"status が 'approved' ではありません(現在: '{item.get('status')}')")
    angle_data = next((a for a in item["angles"] if a["type"] == angle), None)
    if angle_data is None:
        raise PublishError(f"angle '{angle}' が見つかりません")

    import social_visuals as sv
    tags = item.get("tags", [])
    sv.make_hook_slide(tags, angle_data["hook"], angle, slug)
    sv.make_carousel_slides(angle_data["carousel"], angle, slug, tags)
    sv.make_cta_slide(slug, angle_data.get("cta"), angle)

    files = collect_slide_files(slug, angle)
    print(f"[{slug}/{angle}] 画像{len(files)}枚を再生成して確認しました")

    caption = angle_data.get("caption_tiktok", "")

    if not live:
        print("(dry run: 実際の投稿は行いません。--live を付けると実行します)")
        return {"live": False, "files": [f.name for f in files]}

    token = os.environ.get("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise PublishError("TIKTOK_ACCESS_TOKEN が.envにありません。先にsocial_tiktok_auth.pyで認証してください。")

    urls = publish_images_to_pages(slug, f"tiktok_{angle}", files)
    print("公開URL:")
    for u in urls:
        print(f"  {u}")

    from social_publish import _wait_urls_live
    print("画像がGitHub Pagesで実際に開けるようになるまで待機します...")
    _wait_urls_live(urls)
    print("画像の反映を確認しました。TikTokへ投稿します。")

    payload = {
        "post_info": {
            "title": caption[:150],
            "privacy_level": "SELF_ONLY",
            "disable_comment": False,
            "auto_add_music": True,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "photo_cover_index": 0,
            "photo_images": urls,
        },
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }
    # 審査が通るまでprivacy_levelはSELF_ONLY(自分にしか見えない)固定。
    # 審査後、公開したくなったらPUBLIC_TO_EVERYONE等に変更する。

    result = _api_call("/post/publish/content/init/", token, payload)
    publish_id = result.get("data", {}).get("publish_id")
    if not publish_id:
        raise PublishError(f"投稿開始に失敗しました: {result}")
    print(f"投稿処理開始: publish_id={publish_id}")

    for _ in range(20):
        status = _api_call("/post/publish/status/fetch/", token, {"publish_id": publish_id})
        state = status.get("data", {}).get("status")
        print(f"  status: {state}")
        if state in ("PUBLISH_COMPLETE", "FAILED"):
            break
        time.sleep(5)

    item["status"] = "published_tiktok"
    item["tiktok_publish_id"] = publish_id
    queue[slug] = item
    SOCIAL_QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"live": True, "publish_id": publish_id, "final_status": state}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使い方: python social_tiktok_publish.py <slug> <angle> [--live]")
        sys.exit(1)
    try:
        res = publish_to_tiktok(sys.argv[1], sys.argv[2], live="--live" in sys.argv)
        print(res)
    except PublishError as e:
        print(f"エラー: {e}")
        sys.exit(1)
