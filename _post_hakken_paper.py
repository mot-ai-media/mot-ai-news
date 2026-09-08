"""Hakkenの2本目のカルーセル投稿。ユーザーが送った論文スクショ(英語版、IMG_1290)を
フック画像の背景として使い、"opportunity"アングルで投稿する一回限りのスクリプト。"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageDraw

import social_visuals as sv

SRC_IMAGE = Path(r"C:\Users\kodama\Downloads\IMG_1290.PNG")
BASE_DIR = Path(__file__).parent
SLUG = "sony-ai-hakken-d6a8aa14"
ANGLE = "opportunity"
GRAPH_API = "https://graph.instagram.com/v21.0"
SITE_BASE_URL = "https://mot-ai-media.github.io/mot-ai-news"


def build_hook_image(hook: str) -> Path:
    paper = Image.open(SRC_IMAGE)
    # スマホのステータスバー(上下の黒帯)を除いた本文部分だけを切り出す
    cropped = paper.crop((0, 460, 1242, 2100))

    scale = sv.SIZE[0] / cropped.width
    new_h = round(cropped.height * scale)
    resized = cropped.resize((sv.SIZE[0], new_h))
    canvas = Image.new("RGB", sv.SIZE, (255, 255, 255))
    y_off = (sv.SIZE[1] - new_h) // 2
    canvas.paste(resized, (0, y_off))

    draw = ImageDraw.Draw(canvas)
    scrim_height = 700
    scrim = Image.new("L", (1, scrim_height), 0)
    for y in range(scrim_height):
        ratio = y / scrim_height
        scrim.putpixel((0, y), int(252 * min(1.0, ratio * 1.8)))
    scrim = scrim.resize((sv.SIZE[0], scrim_height))
    black = Image.new("RGB", (sv.SIZE[0], scrim_height), (0, 0, 0))
    canvas.paste(black, (0, sv.SIZE[1] - scrim_height), scrim)

    draw = ImageDraw.Draw(canvas)
    max_text_width = sv.SIZE[0] - 140
    font_hook, lines = sv._fit_text(draw, hook, sv.FONT_BOLD, max_text_width, min_size=48, max_size=84, max_lines=3)
    line_h = int(font_hook.size * 1.22)
    total_h = len(lines) * line_h
    y = sv.SIZE[1] - 150 - total_h
    for line in lines:
        draw.text((70, y), line, font=font_hook, fill=(255, 255, 255))
        y += line_h

    sv._paste_watermark(canvas)

    out_path = BASE_DIR / "social_assets" / f"{SLUG}_{ANGLE}_hook.png"
    canvas.save(out_path)
    return out_path


def main() -> None:
    load_dotenv(BASE_DIR.parent / ".env")
    queue = json.loads((BASE_DIR / "social_queue.json").read_text(encoding="utf-8"))
    item = queue[SLUG]
    angle_data = next(a for a in item["angles"] if a["type"] == ANGLE)

    # 自動改行だと読点だけが単独行になり読みにくいため、画像描画専用に手動で整形する
    hook_display = "新しい薬 新しい治療法\nAIが最短ルートを示す"
    print("hook:", hook_display)
    build_hook_image(hook_display)

    # slide2/slide3/CTAは通常通り(記事のタグから選ぶ厳選背景)再生成する
    tags = item.get("tags", [])
    sv.make_carousel_slides(angle_data["carousel"], ANGLE, SLUG, tags, "", None)
    sv.make_cta_slide(SLUG, angle_data.get("cta"), ANGLE)

    files = [
        BASE_DIR / "social_assets" / f"{SLUG}_{ANGLE}_hook.png",
        BASE_DIR / "social_assets" / f"{SLUG}_{ANGLE}_slide2.png",
        BASE_DIR / "social_assets" / f"{SLUG}_{ANGLE}_slide3.png",
        BASE_DIR / "social_assets" / f"{SLUG}_{ANGLE}_cta.png",
    ]
    for f in files:
        assert f.exists(), f"missing: {f}"

    import subprocess

    version = time.strftime("%Y%m%d%H%M%S")
    target_dir = BASE_DIR / "docs" / "social" / SLUG / f"{ANGLE}_{version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        (target_dir / f.name).write_bytes(f.read_bytes())

    subprocess.run(["git", "add", str(target_dir)], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "commit", "-m", f"SNS投稿用画像を追加(論文スクショ使用): {SLUG}/{ANGLE}"], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "push"], cwd=BASE_DIR, check=True)

    urls = [f"{SITE_BASE_URL}/social/{SLUG}/{ANGLE}_{version}/{f.name}" for f in files]
    for u in urls:
        print(u)

    print("GitHub Pagesへの反映を待機します...")
    start = time.time()
    for url in urls:
        while True:
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        break
            except (urllib.error.HTTPError, urllib.error.URLError):
                pass
            if time.time() - start > 180:
                raise RuntimeError("タイムアウト: " + url)
            time.sleep(5)
    print("反映確認。投稿します。")

    token = os.environ["INSTAGRAM_LONG_LIVED_TOKEN"]
    ig_user_id = os.environ["INSTAGRAM_USER_ID"]

    def _api(method: str, url: str, params: dict) -> dict:
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(f"{url}?{data.decode()}" if method == "GET" else url,
                                      data=None if method == "GET" else data, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Graph APIエラー({e.code}): {e.read().decode('utf-8', errors='replace')}") from None

    def _wait_ready(cid: str) -> None:
        start2 = time.time()
        while True:
            status = _api("GET", f"{GRAPH_API}/{cid}", {"fields": "status_code", "access_token": token})
            code = status.get("status_code")
            if code == "FINISHED":
                return
            if code == "ERROR":
                raise RuntimeError(f"コンテナ処理失敗: {cid}")
            if time.time() - start2 > 90:
                raise RuntimeError(f"タイムアウト: {cid}")
            time.sleep(3)

    child_ids = []
    for url in urls:
        result = _api("POST", f"{GRAPH_API}/{ig_user_id}/media", {
            "image_url": url, "is_carousel_item": "true", "access_token": token,
        })
        cid = result["id"]
        _wait_ready(cid)
        child_ids.append(cid)
        print("画像コンテナ作成完了:", len(child_ids))

    caption = angle_data.get("caption_instagram", "")
    parent = _api("POST", f"{GRAPH_API}/{ig_user_id}/media", {
        "media_type": "CAROUSEL", "children": ",".join(child_ids), "caption": caption, "access_token": token,
    })
    parent_id = parent["id"]
    _wait_ready(parent_id)

    publish = _api("POST", f"{GRAPH_API}/{ig_user_id}/media_publish", {
        "creation_id": parent_id, "access_token": token,
    })
    print("投稿完了。media_id:", publish["id"])


if __name__ == "__main__":
    main()
