"""SNS投稿用の画像(フックスライド+CTAスライド)をPillowで生成する。

参考にした実例(wakaru_lab.jp等)のフォーマットに合わせ、「写真フルサイズ+下部に太字テキスト」
の構成にする。記事の実画像があればそれを背景に使い、無ければ既存サイトと同じ配色ロジックの
グラデーションにフォールバックする。

サイズは4:5(1080x1350)。Instagramのカルーセル投稿が公式にサポートするアスペクト比は
1:1・4:5・1.91:1のみで、9:16(Reels/Stories用)は対象外(規格外だとフィード上で
リールのように扱われる/意図しない見え方になる)。フィード用カルーセルなので4:5を採用する。
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
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
    "ビジネス": "ai_glow", "資金調達": "ai_glow", "IPO": "ai_glow", "スタートアップ": "ai_glow",
    "雇用": "ai_glow", "働き方": "ai_glow", "IT人材": "ai_glow",
}
# デフォルト(タグ不一致時の受け皿)は「AIメディアなのに一番よく出る画像が一番AIっぽくない
# 汎用デスク写真」という指摘を受け、抽象的でテクノロジー感のあるビジュアル(ai_glow)に変更。
# officeカテゴリの写真自体は残すが、既定では使われない。
DEFAULT_BG_CATEGORY = "ai_glow"

# 記事タグに著名人が含まれる場合は、無関係な汎用カテゴリ写真ではなく、その人物本人の
# 実写真(Wikimedia Commonsの商用利用可能なCCライセンス写真)を使う。
# ライセンスがクレジット表記を要求する場合、フック(1枚目)スライドの隅に小さく表示する。
PEOPLE_DIR = BG_PHOTOS_DIR / "people"
_PEOPLE_META_PATH = PEOPLE_DIR / "_meta.json"
try:
    _PEOPLE_META: dict = json.loads(_PEOPLE_META_PATH.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError):
    _PEOPLE_META = {}

NAMED_FIGURE_TAG_MAP: dict[str, str] = {}
for _person_key, _info in _PEOPLE_META.items():
    for _tag in _info.get("tags", []):
        NAMED_FIGURE_TAG_MAP[_tag] = _person_key

# 同じ背景写真の使い回し防止。カテゴリごとに複数枚(social_bg_photos/{category}*.jpg)を
# 用意し、直近BG_REUSE_COOLDOWN_DAYS日以内に使った写真は避けて選ぶ。
BG_USAGE_STATE_PATH = Path(__file__).parent / "social_bg_usage.json"
BG_REUSE_COOLDOWN_DAYS = 30
# 同一プロセス内(=1回の記事生成)ではhook/中間スライド/CTAで同じ写真を使い続けたいので、
# (category, seed)ごとに1回だけ選び、使用履歴の更新も1回だけにするためのキャッシュ。
_bg_pick_cache: dict[tuple[str, str], "Path | None"] = {}

# プールが尽きた(直近30日以内に使っていない写真が無い)場合、Pexels検索APIで
# カテゴリに合う新しい写真を自動取得してプールに追加する。手動での定期補充を不要にする。
# PEXELS_API_KEYが無い(=未設定)場合は静かにスキップし、従来通り最も古い写真を再利用する。
PEXELS_SEARCH_TERMS = {
    "robot": "humanoid robot technology",
    "chip": "computer chip semiconductor closeup",
    "office": "modern office workspace",
    "code": "programming code screen",
    "security": "cybersecurity digital",
    "network": "data center server room",
    "ai_glow": "abstract neural network digital technology",
}
PEXELS_IDS_STATE_PATH = BG_PHOTOS_DIR / "_pexels_fetched_ids.json"


def _load_pexels_fetched_ids() -> dict[str, list[int]]:
    try:
        return json.loads(PEXELS_IDS_STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _fetch_new_bg_photo(category: str) -> Path | None:
    """Pexels検索APIでカテゴリに合う新しい写真を1枚探してダウンロードし、プールに追加する。
    APIキー未設定・検索失敗・ダウンロード失敗など、何かあれば静かにNoneを返す
    (呼び出し側は既存プールへのフォールバックで対応済みなので、ここで例外を投げて
    投稿処理全体を止めない)。"""
    api_key = os.environ.get("PEXELS_API_KEY")
    query = PEXELS_SEARCH_TERMS.get(category)
    if not api_key or not query:
        return None

    fetched = _load_pexels_fetched_ids()
    already_fetched = set(fetched.get(category, []))

    try:
        search_url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
            {"query": query, "per_page": 20, "orientation": "portrait"}
        )
        # PexelsのCloudflare WAFがデフォルトのUser-Agent(urllib標準)をボット判定してブロックする
        # (403 error code 1010)ため、ブラウザ相当のUser-Agentを明示的に付ける。
        req = urllib.request.Request(search_url, headers={
            "Authorization": api_key,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            results = json.loads(resp.read().decode("utf-8")).get("photos", [])

        candidate = next((p for p in results if p["id"] not in already_fetched), None)
        if not candidate:
            return None

        image_url = candidate["src"]["large2x"]
        img_req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 (compatible; MOTBot/1.0)"})
        with urllib.request.urlopen(img_req, timeout=15) as resp:
            data = resp.read()

        existing = sorted(BG_PHOTOS_DIR.glob(f"{category}_*.jpg"))
        next_n = 1 + max([int(f.stem.split("_")[-1]) for f in existing], default=1)
        dest = BG_PHOTOS_DIR / f"{category}_{next_n}.jpg"
        dest.write_bytes(data)

        fetched.setdefault(category, []).append(candidate["id"])
        PEXELS_IDS_STATE_PATH.write_text(json.dumps(fetched, ensure_ascii=False, indent=2), encoding="utf-8")
        return dest
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, OSError):
        return None

FONT_BOLD = "C:/Windows/Fonts/YuGothB.ttc"
FONT_REGULAR = "C:/Windows/Fonts/YuGothR.ttc"

SIZE = (1080, 1350)  # Instagramカルーセル対応比率(4:5)

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


def _load_bg_usage() -> dict[str, str]:
    try:
        return json.loads(BG_USAGE_STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_bg_usage(usage: dict[str, str]) -> None:
    BG_USAGE_STATE_PATH.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")


def _pick_bg_file(category: str, seed: str) -> Path | None:
    """カテゴリ内の候補写真(social_bg_photos/{category}*.jpg)から、直近
    BG_REUSE_COOLDOWN_DAYS日以内に使っていないものを優先して選ぶ。
    全部使用済みの場合は、最も古く使われた写真を選ぶ(使い回しの偏りを最小化)。"""
    cache_key = (category, seed)
    if cache_key in _bg_pick_cache:
        return _bg_pick_cache[cache_key]

    candidates = sorted(BG_PHOTOS_DIR.glob(f"{category}*.jpg"))
    if not candidates:
        _bg_pick_cache[cache_key] = None
        return None

    usage = _load_bg_usage()
    now = datetime.now()

    def days_since_used(name: str) -> float:
        used_at = usage.get(name)
        if not used_at:
            return float("inf")
        try:
            return (now - datetime.fromisoformat(used_at)).total_seconds() / 86400
        except ValueError:
            return float("inf")

    eligible = [c for c in candidates if days_since_used(c.name) >= BG_REUSE_COOLDOWN_DAYS]
    if not eligible:
        # プールが尽きた場合、まずPexels検索APIで新しい写真の自動取得を試みる
        # (手動での定期補充を不要にするため)。取得できなければ最も古く使われた
        # 1枚を再利用する(=最善努力で偏りを避ける、フォールバック)。
        fetched = _fetch_new_bg_photo(category)
        if fetched is not None:
            pool = [fetched]
        else:
            pool = [max(candidates, key=lambda c: days_since_used(c.name))]
    else:
        pool = eligible

    idx = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % len(pool)
    chosen = pool[idx]

    usage[chosen.name] = now.isoformat()
    _save_bg_usage(usage)
    _bg_pick_cache[cache_key] = chosen
    return chosen


def _curated_background(tags: list[str] | None, seed: str, angle: str | None = None) -> Image.Image:
    """記事のタグから、MOTが厳選したフリー素材(social_bg_photos/)を選んで背景にする。
    元記事のスクショ的な画像(質のばらつき・著作権グレー)は使わない。カテゴリ内に複数枚
    あれば直近使っていないものをローテーションで選ぶ(_pick_bg_file)。
    素材が無い等の異常時のみグラデーションにフォールバックする。"""
    category = pick_bg_category(tags, angle)
    path = _pick_bg_file(category, seed)
    if path is None:
        return _gradient_background(seed)
    try:
        photo = Image.open(path).convert("RGB")
        return _cover_crop(photo)
    except OSError:
        return _gradient_background(seed)


def pick_named_figure(tags: list[str] | None) -> str | None:
    """記事タグに著名人が含まれていればその人物キーを返す(例: 「ビル・ゲイツ」→"bill_gates")。"""
    for tag in tags or []:
        if tag in NAMED_FIGURE_TAG_MAP:
            return NAMED_FIGURE_TAG_MAP[tag]
    return None


def _background_for_article(
    tags: list[str] | None, seed: str, angle: str | None = None, image_url: str | None = None,
) -> tuple[Image.Image, str | None]:
    """背景選択の優先順位:
    1. 著名人が写っていれば本人の実写真(既存ロジック、最優先)
    2. それ以外は4記事に1記事だけMOT厳選の背景写真(ai_glow等)を使い、
       残り3/4は元記事の実画像を引用する(ユーザー指示による方針)
    3. 元記事画像の取得に失敗した場合のみ厳選写真にフォールバック
    戻り値の2つ目はクレジット表記(表示不要ならNone)。"""
    person_key = pick_named_figure(tags)
    if person_key:
        path = PEOPLE_DIR / f"{person_key}.jpg"
        try:
            photo = Image.open(path).convert("RGB")
            credit = _PEOPLE_META.get(person_key, {}).get("credit")
            return _cover_crop(photo), credit
        except OSError:
            pass

    use_curated = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % 4 == 0
    if not use_curated:
        fetched = _fetch_photo_background(image_url)
        if fetched is not None:
            return fetched, None
    return _curated_background(tags, seed, angle), None


def _fetch_photo_background(image_url: str | None) -> Image.Image | None:
    """元記事の実画像を取得して背景にする。取得失敗時はNone(呼び出し側でcuratedにフォールバック)。"""
    if not image_url:
        return None
    try:
        request = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 (compatible; MOTBot/1.0)"})
        with urllib.request.urlopen(request, timeout=10) as resp:
            photo = Image.open(BytesIO(resp.read())).convert("RGB")
        return _cover_crop(photo)
    except Exception:
        return None


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


def make_hook_slide(
    tags: list[str] | None, hook: str, angle: str, slug: str, source: str = "",
    image_url: str | None = None,
) -> Path:
    """タグから選んだ厳選フリー素材を背景に、下部に太字フックテキストを重ねる。
    参考にした実例(nicocinojp等)に合わせ、色帯や大きなロゴ表記は使わず、
    中央上部に小さなロゴのワンポイントだけを添える控えめなブランディングにする。
    記事タグに著名人がいれば汎用カテゴリ写真より優先してその人物の実写真を使う。"""
    img, photo_credit = _background_for_article(tags, source or slug, angle, image_url)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    # 下部を読みやすくする暗いグラデーションのスクリム
    scrim_height = 534
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
    font_hook, lines = _fit_text(draw, hook, FONT_BOLD, max_text_width, min_size=48, max_size=84, max_lines=3)
    line_h = int(font_hook.size * 1.22)
    total_h = len(lines) * line_h
    y = SIZE[1] - 155 - total_h
    for line in lines:
        draw.text((70, y), line, font=font_hook, fill=(255, 255, 255))
        y += line_h

    _paste_watermark(img)

    if photo_credit:
        # CC BY / CC BY-SA等、クレジット表記が必要なライセンスの写真を使った場合のみ表示。
        # カルーセル全体で1回で十分なので、1枚目(フック)だけに載せる。
        font_credit = ImageFont.truetype(FONT_REGULAR, 20)
        credit_text = f"Photo: {photo_credit}"
        w = draw.textlength(credit_text, font=font_credit)
        draw.text((SIZE[0] - w - 20, SIZE[1] - 34), credit_text, font=font_credit, fill=(200, 200, 205))

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{slug}_{angle}_hook.png"
    img.save(out_path)
    return out_path


def make_text_slide(
    text: str, step: int, total: int, angle: str, slug: str,
    tags: list[str] | None = None, source: str = "",
    image_url: str | None = None,
) -> Path:
    """カルーセル中間スライド。文字だけの単調な画面を避け、フックと同じ背景写真
    (同カテゴリなので同じ画像になる)を再利用し、その上に読みやすさ優先の暗いオーバーレイ
    を重ねてテキストを載せる。色帯は使わず、控えめなブランディングで統一する。"""
    img, _ = _background_for_article(tags, source or slug, angle, image_url)
    img = img.convert("RGB")

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
    draw.text((90, SIZE[1] - 55), f"{step}/{total}", font=font_step, fill=(180, 180, 190))

    _paste_watermark(img)

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{slug}_{angle}_slide{step}.png"
    img.save(out_path)
    return out_path


def make_carousel_slides(
    carousel_texts: list[str], angle: str, slug: str,
    tags: list[str] | None = None, source: str = "",
    image_url: str | None = None,
) -> list[Path]:
    """カルーセルの中間スライド群(通常2枚)を作る。フック(1枚目)・CTA(最終枚)と合わせて
    合計4枚のスライド投稿になる想定。"""
    total = len(carousel_texts) + 2  # hook + 中間 + cta
    paths = []
    for i, text in enumerate(carousel_texts):
        paths.append(make_text_slide(text, i + 2, total, angle, slug, tags, source, image_url))
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
        logo_w = 366
        logo = logo.resize((logo_w, logo_w))
        img.paste(logo, ((SIZE[0] - logo_w) // 2, 200), logo)
    except FileNotFoundError:
        pass

    font_cta, lines = _fit_text(draw, cta_text, FONT_BOLD, SIZE[0] - 160, min_size=32, max_size=52, max_lines=4)
    line_h = int(font_cta.size * 1.25)
    y = 720
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
