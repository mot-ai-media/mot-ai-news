"""SNS投稿用の画像(フックスライド+CTAスライド)をPillowで生成する。

参考にした実例(wakaru_lab.jp等)のフォーマットに合わせ、Reels/TikTok向けの縦長(9:16)、
「写真フルサイズ+下部に太字テキスト」の構成にする。記事の実画像があればそれを背景に使い、
無ければ既存サイトと同じ配色ロジックのグラデーションにフォールバックする。
"""

from __future__ import annotations

import hashlib
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT_DIR = Path(__file__).parent / "social_assets"
LOGO_PATH = Path(__file__).parent / "docs" / "og-image.png"

FONT_BOLD = "C:/Windows/Fonts/YuGothB.ttc"
FONT_REGULAR = "C:/Windows/Fonts/YuGothR.ttc"

SIZE = (1080, 1920)  # Reels/TikTok縦長比率(9:16)

ANGLE_COLORS = {
    "fear": (239, 68, 68),
    "surprise": (245, 158, 11),
    "opportunity": (16, 185, 129),
    "practical": (37, 99, 235),
}

# build_site.pyのFALLBACK_GRADIENTSと同じ配色思想(実画像が無い記事向け)
FALLBACK_GRADIENTS = [
    ((26, 26, 46), (58, 58, 104)),
    ((15, 32, 39), (44, 83, 100)),
    ((35, 37, 38), (65, 67, 69)),
    ((22, 34, 42), (58, 96, 115)),
    ((48, 43, 99), (15, 12, 41)),
    ((30, 60, 50), (45, 106, 79)),
]

CTA_POOL = [
    "AIの「今」を、置いていかれる前に。",
    "知らないと差がつく、今日のAIニュース。",
    "AIをやさしく理解できるメディア、MOT。",
    "変化に気づける人でいよう。",
    "今日のAI、3分でわかる。",
]


def _pick_gradient(seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    idx = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % len(FALLBACK_GRADIENTS)
    return FALLBACK_GRADIENTS[idx]


def _gradient_background(seed: str) -> Image.Image:
    c1, c2 = _pick_gradient(seed)
    img = Image.new("RGB", SIZE, c1)
    draw = ImageDraw.Draw(img)
    for y in range(SIZE[1]):
        t = y / SIZE[1]
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(0, y), (SIZE[0], y)], fill=(r, g, b))
    return img


def _fetch_photo_background(image_url: str | None, seed: str) -> Image.Image:
    """記事の実画像を取得して背景いっぱいにトリミングする。取得失敗時はグラデーションにフォールバック。"""
    if image_url:
        try:
            request = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 (compatible; MOTBot/1.0)"})
            with urllib.request.urlopen(request, timeout=10) as resp:
                photo = Image.open(BytesIO(resp.read())).convert("RGB")
            # SIZEのアスペクト比に合わせてカバー(はみ出た分は中央基準でクロップ)
            src_ratio = photo.width / photo.height
            dst_ratio = SIZE[0] / SIZE[1]
            if src_ratio > dst_ratio:
                new_height = SIZE[1]
                new_width = int(new_height * src_ratio)
            else:
                new_width = SIZE[0]
                new_height = int(new_width / src_ratio)
            photo = photo.resize((new_width, new_height))
            left = (new_width - SIZE[0]) // 2
            top = (new_height - SIZE[1]) // 2
            return photo.crop((left, top, left + SIZE[0], top + SIZE[1]))
        except Exception:
            pass
    return _gradient_background(seed)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for ch in text:
        test = line + ch
        if draw.textlength(test, font=font) > max_width and line:
            lines.append(line)
            line = ch
        else:
            line = test
    if line:
        lines.append(line)
    return lines


def make_hook_slide(image_url: str | None, hook: str, angle: str, slug: str, source: str = "") -> Path:
    """記事の実画像(無ければグラデーション)を背景に、下部に太字フックテキストを重ねる。
    右下にMOTの小さなロゴを置き、アングルカラーの帯を左端に添える。"""
    img = _fetch_photo_background(image_url, source or slug).convert("RGB")
    draw = ImageDraw.Draw(img)

    # 下部を読みやすくする暗いグラデーションのスクリム
    scrim_height = 760
    scrim = Image.new("L", (1, scrim_height), 0)
    for y in range(scrim_height):
        scrim.putpixel((0, y), int(230 * (y / scrim_height)))
    scrim = scrim.resize((SIZE[0], scrim_height))
    black = Image.new("RGB", (SIZE[0], scrim_height), (0, 0, 0))
    img.paste(black, (0, SIZE[1] - scrim_height), scrim)

    draw = ImageDraw.Draw(img)

    # アングルカラーの帯(左端)
    color = ANGLE_COLORS.get(angle, (37, 99, 235))
    draw.rectangle([(0, 0), (16, SIZE[1])], fill=color)

    # フックテキスト(下部、太字・大きめ)
    font_hook = ImageFont.truetype(FONT_BOLD, 84)
    max_text_width = SIZE[0] - 140
    lines = _wrap_text(draw, hook, font_hook, max_text_width)
    total_h = len(lines) * 100
    y = SIZE[1] - 220 - total_h
    for line in lines:
        draw.text((70, y), line, font=font_hook, fill=(255, 255, 255))
        y += 100

    # ブランド表記(右下、小さく)
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo = logo.resize((72, 72))
        img.paste(logo, (SIZE[0] - 110, SIZE[1] - 110), logo)
    except FileNotFoundError:
        pass
    font_brand = ImageFont.truetype(FONT_REGULAR, 30)
    draw.text((70, SIZE[1] - 70), "MOT", font=font_brand, fill=(230, 230, 235))

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{slug}_{angle}_hook.png"
    img.save(out_path)
    return out_path


def make_cta_slide(slug: str) -> Path:
    """動画・投稿の最後に使うMOT宣伝スライド。CTA文はスラッグのハッシュで決定的にローテーションする
    (build_site.pyの_pick_ad()と同じ考え方: 同じ記事は毎回同じ文になり、全体では分散する)。"""
    idx = int(hashlib.sha1(slug.encode("utf-8")).hexdigest(), 16) % len(CTA_POOL)
    cta_text = CTA_POOL[idx]

    img = Image.new("RGB", SIZE, (10, 10, 12))
    draw = ImageDraw.Draw(img)

    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo_w = 520
        logo = logo.resize((logo_w, logo_w))
        img.paste(logo, ((SIZE[0] - logo_w) // 2, 560), logo)
    except FileNotFoundError:
        pass

    font_cta = ImageFont.truetype(FONT_BOLD, 52)
    lines = _wrap_text(draw, cta_text, font_cta, SIZE[0] - 160)
    y = 1230
    for line in lines:
        w = draw.textlength(line, font=font_cta)
        draw.text(((SIZE[0] - w) / 2, y), line, font=font_cta, fill=(255, 255, 255))
        y += 66

    font_sub = ImageFont.truetype(FONT_REGULAR, 32)
    sub = "続きはMOTで"
    w = draw.textlength(sub, font=font_sub)
    draw.text(((SIZE[0] - w) / 2, y + 30), sub, font=font_sub, fill=(150, 150, 160))

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{slug}_cta.png"
    img.save(out_path)
    return out_path
