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

from janome.tokenizer import Tokenizer
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# 形態素解析器(1プロセスにつき1回だけ初期化。辞書ロードに時間がかかるため使い回す)。
# 「攻撃」のような熟語が文字幅の都合で「攻」「撃」に割れるのを防ぐため、
# 折り返しは文字単位ではなく単語(形態素)単位で行う。
_TOKENIZER = Tokenizer()

OUT_DIR = Path(__file__).parent / "social_assets"
LOGO_PATH = Path(__file__).parent / "docs" / "og-image.png"
WATERMARK_LOGO_PATH = Path(__file__).parent / "MOT logo.png"  # 文字無しのマークのみ版(小さく使う用)
BG_PHOTOS_DIR = Path(__file__).parent / "social_bg_photos"

# 記事のタグ→背景写真カテゴリの対応。元記事のスクショ的な画像(質にばらつき、著作権グレー)は
# もう使わず、MOTが厳選したPexelsのフリー素材(商用利用無料・帰属表示不要)に統一する。
TAG_CATEGORY_MAP = {
    "ロボット": "robot", "ロボティクス": "robot", "ヒューマノイド": "robot",
    "ヒューマノイドロボット": "robot", "自動運転": "robot", "Robotics": "robot",
    "Nvidia": "chip", "NVIDIA": "chip", "半導体": "chip", "TSMC": "chip",
    "チップ": "chip", "GPU": "chip", "推論最適化": "chip",
    "GitHub": "code", "プログラミング": "code", "OSS": "code", "オープンソース": "code",
    "開発者": "code", "コーディング": "code", "Cursor": "code", "Codex": "code",
    "セキュリティ": "security", "ハッキング": "security", "サイバー攻撃": "security",
    "プライバシー": "security", "規制": "security", "偽情報": "security",
    "データセンター": "network", "クラウド": "network", "インフラ": "network", "半導体工場": "network",
    "ビジネス": "office", "資金調達": "office", "IPO": "office", "スタートアップ": "office",
    "雇用": "office", "働き方": "office", "IT人材": "office",
}
DEFAULT_BG_CATEGORY = "office"

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


def _cover_crop(photo: Image.Image) -> Image.Image:
    """SIZEのアスペクト比に合わせて画像をカバー表示(はみ出た分は中央基準でクロップ)。"""
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


def pick_bg_category(tags: list[str] | None, angle: str | None = None) -> str:
    """タグが何にもマッチしない場合、officeに一律フォールバックすると
    (例: 「AIが結託して攻撃」のような物騒な話でも呑気なオフィス写真になる)内容と
    写真が食い違う事故が起きる。fearアングルはタグ不一致時、securityへ寄せる。"""
    for tag in tags or []:
        if tag in TAG_CATEGORY_MAP:
            return TAG_CATEGORY_MAP[tag]
    if angle == "fear":
        return "security"
    return DEFAULT_BG_CATEGORY


def _curated_background(tags: list[str] | None, seed: str, angle: str | None = None) -> Image.Image:
    """記事のタグから、MOTが厳選したフリー素材(social_bg_photos/)を選んで背景にする。
    元記事のスクショ的な画像(質のばらつき・著作権グレー)は使わない。
    素材フォルダが無い等の異常時のみグラデーションにフォールバックする。"""
    category = pick_bg_category(tags, angle)
    path = BG_PHOTOS_DIR / f"{category}.jpg"
    try:
        photo = Image.open(path).convert("RGB")
        return _cover_crop(photo)
    except (FileNotFoundError, OSError):
        return _gradient_background(seed)


def _fetch_photo_background(image_url: str | None, seed: str) -> Image.Image:
    """(未使用/予備) 記事の実画像を取得して背景にする従来方式。質のばらつき・著作権の懸念から
    現在はcuratedな自社素材(_curated_background)に切り替え済み。"""
    if image_url:
        try:
            request = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 (compatible; MOTBot/1.0)"})
            with urllib.request.urlopen(request, timeout=10) as resp:
                photo = Image.open(BytesIO(resp.read())).convert("RGB")
            return _cover_crop(photo)
        except Exception:
            pass
    return _gradient_background(seed)


def _paste_watermark(img: Image.Image, size: int = 64) -> None:
    """中央上部に小さくロゴマークだけを添える(参考にした実例のワンポイント配置に合わせる)。
    帯や大きなロゴ表記は使わない、控えめなブランディング。"""
    try:
        logo = Image.open(WATERMARK_LOGO_PATH).convert("RGBA")
    except FileNotFoundError:
        return
    logo = logo.resize((size, size))
    img.paste(logo, ((SIZE[0] - size) // 2, 56), logo)


_COUNTER_UNITS = set("体人件社回個年月日円万億台本枚匹頭")

# 助詞1文字は形態素解析でも独立トークンになるが、それが行頭に来ると不自然
# (「AIが人間を」の次の行が「指示なく」ではなく「は」だけで始まる等)。
_LEADING_PARTICLES = {
    "は", "が", "を", "に", "で", "と", "も", "の", "へ", "や",
    "から", "まで", "より", "だけ", "など",
}


def _tokenize_for_wrap(text: str) -> list[str]:
    """MOT SNS Typography System: 文字幅ではなく単語(形態素)単位で折り返せるよう
    形態素解析する。「攻撃」のような熟語が「攻」「撃」に割れる事故を防ぐのが目的。
    数字("1200")の直後に単位(体/人等)が来る場合はさらに結合して1トークンにする。"""
    tokens = [tok.surface for tok in _TOKENIZER.tokenize(text)]
    merged: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.isdigit() and i + 1 < len(tokens) and tokens[i + 1] in _COUNTER_UNITS:
            merged.append(tok + tokens[i + 1])
            i += 2
        else:
            merged.append(tok)
            i += 1
    return merged


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """幅に応じて折り返す。MOT SNS Typography System:
    - 形態素解析で単語単位に分割し、熟語(「攻撃」等)や固有名詞(「OpenAI」等)、
      数字+単位(「1200体」等)が単語の途中で割れないようにする
    - 行末が1〜2文字だけの孤立行にならないよう前の行へ結合する(幅を超える場合は結合しない)
    - 行頭が単独の助詞(「は」「が」等)だけで始まらないよう前の行へ戻す"""
    tokens = _tokenize_for_wrap(text)
    lines: list[str] = []
    line = ""
    for tok in tokens:
        test = line + tok
        if draw.textlength(test, font=font) > max_width and line:
            lines.append(line)
            line = tok
        else:
            line = test
    if line:
        lines.append(line)

    # 孤立行の防止: 最終行が1〜2文字だけだと「した」のように寂しく浮いて見える。
    # ただし前の行に吸収してmax_widthを超えるとキャンバス外にはみ出すため、
    # 厳密にmax_width以内に収まる場合のみ結合する(はみ出す場合は孤立行のまま残す)。
    if len(lines) >= 2 and len(lines[-1]) <= 2:
        merged = lines[-2] + lines[-1]
        if draw.textlength(merged, font=font) <= max_width:
            lines[-2] = merged
            lines.pop()

    # 行頭の孤立助詞の防止: 2行目以降が助詞だけで始まる場合、前の行の末尾に戻す
    # (幅を超えない場合のみ。超える場合はそのまま残す=はみ出しを絶対に作らない)
    i = 1
    while i < len(lines):
        particle = next((p for p in _LEADING_PARTICLES if lines[i].startswith(p) and len(lines[i]) > len(p)), None)
        if particle:
            candidate = lines[i - 1] + particle
            if draw.textlength(candidate, font=font) <= max_width:
                lines[i - 1] = candidate
                lines[i] = lines[i][len(particle):]
        i += 1

    return lines


def _fit_text(
    draw: ImageDraw.ImageDraw, text: str, font_path: str, max_width: int,
    min_size: int, max_size: int, max_lines: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """「文字が多いから縮小する」ではなく「収まる範囲で最大サイズを選ぶ」判断にする。
    text中の明示的な改行(\\n、AIが意味の区切りで指定したもの)をまず尊重し、
    各行がそれでも幅に収まらない場合のみ_wrap_text()でさらに折り返す。
    max_lines以内に収まる最大フォントサイズを大きい方から探索する。"""
    for size in range(max_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        lines: list[str] = []
        for para in text.split("\n"):
            para = para.strip()
            if para:
                lines.extend(_wrap_text(draw, para, font, max_width))
        if len(lines) <= max_lines:
            return font, lines
    # 最小サイズでも収まらない場合はそのまま返す(情報量を勝手に削らない)
    font = ImageFont.truetype(font_path, min_size)
    lines = []
    for para in text.split("\n"):
        para = para.strip()
        if para:
            lines.extend(_wrap_text(draw, para, font, max_width))
    return font, lines


def make_hook_slide(tags: list[str] | None, hook: str, angle: str, slug: str, source: str = "") -> Path:
    """タグから選んだ厳選フリー素材を背景に、下部に太字フックテキストを重ねる。
    参考にした実例(nicocinojp等)に合わせ、色帯や大きなロゴ表記は使わず、
    中央上部に小さなロゴのワンポイントだけを添える控えめなブランディングにする。"""
    img = _curated_background(tags, source or slug, angle).convert("RGB")
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

    # フックテキスト(下部、太字)。文字数に応じて収まる最大サイズを選ぶ
    # (「文字が多いから縮小」ではなく「短ければ大きく」、余白を無駄にしない)
    max_text_width = SIZE[0] - 140
    font_hook, lines = _fit_text(draw, hook, FONT_BOLD, max_text_width, min_size=56, max_size=100, max_lines=3)
    line_h = int(font_hook.size * 1.22)
    total_h = len(lines) * line_h
    y = SIZE[1] - 220 - total_h
    for line in lines:
        draw.text((70, y), line, font=font_hook, fill=(255, 255, 255))
        y += line_h

    _paste_watermark(img)

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{slug}_{angle}_hook.png"
    img.save(out_path)
    return out_path


def make_text_slide(
    text: str, step: int, total: int, angle: str, slug: str,
    tags: list[str] | None = None, source: str = "",
) -> Path:
    """カルーセル中間スライド。文字だけの単調な画面を避け、フックと同じ背景写真
    (同カテゴリなので同じ画像になる)を再利用し、その上に読みやすさ優先の暗いオーバーレイ
    を重ねてテキストを載せる。色帯は使わず、控えめなブランディングで統一する。"""
    img = _curated_background(tags, source or slug, angle).convert("RGB")

    # 中間スライドは本文が長め(hookより情報量が多い)なので、画面全体に軽めの
    # 暗いオーバーレイをかけて可読性を優先しつつ、背景の質感は残す
    overlay = Image.new("RGB", SIZE, (8, 8, 10))
    img = Image.blend(img, overlay, 0.62)
    draw = ImageDraw.Draw(img)

    max_text_width = SIZE[0] - 180
    font_body, lines = _fit_text(draw, text, FONT_BOLD, max_text_width, min_size=40, max_size=76, max_lines=5)
    line_h = int(font_body.size * 1.3)
    total_h = len(lines) * line_h
    y = (SIZE[1] - total_h) // 2
    for line in lines:
        draw.text((90, y), line, font=font_body, fill=(255, 255, 255))
        y += line_h

    font_step = ImageFont.truetype(FONT_REGULAR, 28)
    draw.text((90, SIZE[1] - 70), f"{step}/{total}", font=font_step, fill=(180, 180, 190))

    _paste_watermark(img)

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{slug}_{angle}_slide{step}.png"
    img.save(out_path)
    return out_path


def make_carousel_slides(
    carousel_texts: list[str], angle: str, slug: str,
    tags: list[str] | None = None, source: str = "",
) -> list[Path]:
    """カルーセルの中間スライド群(通常2枚)を作る。フック(1枚目)・CTA(最終枚)と合わせて
    合計4枚のスライド投稿になる想定。"""
    total = len(carousel_texts) + 2  # hook + 中間 + cta
    paths = []
    for i, text in enumerate(carousel_texts):
        paths.append(make_text_slide(text, i + 2, total, angle, slug, tags, source))
    return paths


def make_cta_slide(slug: str, cta_text: str | None = None, angle: str | None = None) -> Path:
    """動画・投稿の最後に使うMOT宣伝スライド。この記事・アングル固有のCTA文言が
    渡されればそれを使う(汎用テンプレの使い回しは「このニュースと関係ない」と
    離脱を招くため)。渡されなかった場合のみ、スラッグのハッシュで決定的に
    汎用CTA_POOLからローテーションする(build_site.pyの_pick_ad()と同じ考え方)。"""
    is_custom = bool(cta_text)
    if not cta_text:
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

    font_cta, lines = _fit_text(draw, cta_text, FONT_BOLD, SIZE[0] - 160, min_size=34, max_size=56, max_lines=4)
    line_h = int(font_cta.size * 1.25)
    y = 1230
    for line in lines:
        w = draw.textlength(line, font=font_cta)
        draw.text(((SIZE[0] - w) / 2, y), line, font=font_cta, fill=(255, 255, 255))
        y += line_h

    if not is_custom:
        # 汎用CTA_POOL使用時のみ「続きはMOTで」を補足する。
        # 記事固有のCTAは既に文中でMOTへの誘導を含むため、重複表示を避ける。
        font_sub = ImageFont.truetype(FONT_REGULAR, 32)
        sub = "続きはMOTで"
        w = draw.textlength(sub, font=font_sub)
        draw.text(((SIZE[0] - w) / 2, y + 30), sub, font=font_sub, fill=(150, 150, 160))

    OUT_DIR.mkdir(exist_ok=True)
    filename = f"{slug}_{angle}_cta.png" if angle else f"{slug}_cta.png"
    out_path = OUT_DIR / filename
    img.save(out_path)
    return out_path
