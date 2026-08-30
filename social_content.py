"""MOT記事からSNS投稿用コンテンツ(4アングル)を生成する。

対象記事は「重要度」(importance_score、サイト本編の編集判断)ではなく、SNSでの
拡散性・驚き・おすすめ度から合成した social_score で選ぶ。「重要だが地味なニュース」と
「重要度は普通だが驚き・拡散性が高いニュース」は別物、という考え方。
1記事につきClaude API呼び出しは1回で、4アングル分(不安/驚き/機会/実用)すべてを
まとめて生成する(呼び出し回数を増やしてコストを上げない)。元記事は既にMOT編集部が
事実確認・整形した内容(tldr/what_happened/risk_point等)なので、そこから逸脱しないよう
入力として渡す。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import anthropic

MODEL = "claude-haiku-4-5-20251001"
SOCIAL_SCORE_THRESHOLD = 65
DUPLICATE_TOPIC_WINDOW_DAYS = 3  # 同じタグの記事を短期間で連続してSNS化しない
SITE_BASE_URL = "https://mot-ai-media.github.io/mot-ai-news"

ARTICLES_DATA_PATH = Path(__file__).parent / "articles_data.json"
SOCIAL_QUEUE_PATH = Path(__file__).parent / "social_queue.json"

logger = logging.getLogger(__name__)


def social_score(article: dict) -> int:
    """SNS向けの拡散スコア。既存のbuzz_score(驚き・話題性)とrecommend_score(おすすめ度)を
    ブレンドする。importance_score(サイト本編用)とは別軸: 地味だが重要なニュースは
    importance_scoreは高くてもsocial_scoreは低くなり得る。新規のAPI呼び出しは増やさない。"""
    buzz = article.get("buzz_score")
    recommend = article.get("recommend_score")
    if not isinstance(buzz, (int, float)) or not isinstance(recommend, (int, float)):
        return 0
    return round(buzz * 0.6 + recommend * 0.4)

PROMPT_TEMPLATE = """あなたはAIニュースメディア「MOT」のSNS担当編集者です。
以下のMOT記事をもとに、SNS投稿用のコンテンツを4つの切り口(アングル)で作成してください。

MOTは「AIについていけなくなるのが不安な一般の人」向けのメディアです。
恐怖を煽ることだけに頼らず、興味・好奇心・機会・実用性もバランスよく使ってください。

# 元記事(MOTで既に編集済みの内容。事実はここから一歩も出ないこと)
見出し: {headline}
結論: {tldr}
何が起きたか: {what_happened}
なぜ重要か: {why_it_matters}
一般の人への影響: {impact_on_reader}
リスクポイント: {risk_point}
チャンスポイント: {opportunity_point}
記事URL: {url}

# 4つのアングル(type固定、この順で4つ全部作る)
- fear: 「これを知らないと置いていかれるかも」という危機感の切り口(煽りすぎず事実ベースで)
- surprise: 「え、AIってもうそんなことできるの」という驚き・好奇心の切り口
- opportunity: 「これを使えばこんなことができるようになる」という機会の切り口
- practical: 仕事・生活への具体的な実用インパクトの切り口

# フックの型(参考。機械的に当てはめず記事内容に合わせて自然に書くこと。誇張で事実を歪めない)
「ついに○○が変わる」「人間より○○？」「あなたの仕事にも影響？」「○○が当たり前になる？」
「このAI、もう○○できる」「○○するだけで△△」「専門家も驚いた○○」「実は○○だった」
「日本ではまだ知られていない○○」

# 各アングルで作る項目
- hook: 冒頭1秒で目を止めさせる一言。上記の型を参考に。20字前後
- carousel: 画像2〜5枚のスライド投稿用に3枚分のテキスト(何が起きたか/なぜ重要か/変化すること)。各1文の配列
  (実際の投稿は 1.hook画像 → 2〜4.このcarousel3枚 → 5.MOT誘導、の5枚構成になる)
- caption_instagram: Instagram用キャプション。hookで始め2〜3文、最後に軽くハッシュタグ2〜3個
- caption_facebook: Facebook用。IGより会話的・説明的に3〜4文、ハッシュタグは付けない
- caption_tiktok: TikTok用。カジュアルな話し言葉で2文程度、ハッシュタグは最小限
- caption_youtube: YouTube Shorts用。検索されそうな言葉を含めた説明的な1〜2文(タイトル寄り)
- x_post: X投稿本文。120字以内、結論+一言の気づきを中心に
- cta: この記事・アングルに合わせたMOTへの誘導文。20〜30字

# 制約
- 元記事に書かれていない事実(数字・日付・固有名詞)を新たに作らない
- fearアングルでも、恐怖だけで終わらせず誠実なトーンにする
- caption_instagram/facebook/tiktok/youtube/x_postは同じ文の使い回しではなく、
  それぞれのプラットフォームの文体に合わせて書き分けること
- 出力は次のJSON形式のみ。説明や前置き、コードブロック記号は一切つけない
{{"angles": [{{"type": "fear", "hook": "...", "carousel": ["...", "...", "..."], "caption_instagram": "...", "caption_facebook": "...", "caption_tiktok": "...", "caption_youtube": "...", "x_post": "...", "cta": "..."}}, {{"type": "surprise", "hook": "...", "carousel": ["...", "...", "..."], "caption_instagram": "...", "caption_facebook": "...", "caption_tiktok": "...", "caption_youtube": "...", "x_post": "...", "cta": "..."}}, {{"type": "opportunity", "hook": "...", "carousel": ["...", "...", "..."], "caption_instagram": "...", "caption_facebook": "...", "caption_tiktok": "...", "caption_youtube": "...", "x_post": "...", "cta": "..."}}, {{"type": "practical", "hook": "...", "carousel": ["...", "...", "..."], "caption_instagram": "...", "caption_facebook": "...", "caption_tiktok": "...", "caption_youtube": "...", "x_post": "...", "cta": "..."}}]}}
"""

_REQUIRED_ANGLE_TYPES = ("fear", "surprise", "opportunity", "practical")
_REQUIRED_ANGLE_KEYS = (
    "type", "hook", "carousel",
    "caption_instagram", "caption_facebook", "caption_tiktok", "caption_youtube",
    "x_post", "cta",
)


class GenerationError(Exception):
    """生成結果が期待したJSON形式でなかった場合に送出する。"""


def _load_articles() -> list[dict]:
    if not ARTICLES_DATA_PATH.exists():
        return []
    return json.loads(ARTICLES_DATA_PATH.read_text(encoding="utf-8"))


def _load_queue() -> dict:
    if not SOCIAL_QUEUE_PATH.exists():
        return {}
    try:
        return json.loads(SOCIAL_QUEUE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_queue(queue: dict) -> None:
    SOCIAL_QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def _recent_queued_tags(queue: dict, articles_by_slug: dict, now: datetime) -> set[str]:
    """直近DUPLICATE_TOPIC_WINDOW_DAYS以内にキュー投入済みの記事のタグ集合。
    同じ話題を短期間に連続でSNS化しないための重複トピック検出に使う。"""
    cutoff = (now - timedelta(days=DUPLICATE_TOPIC_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M")
    tags: set[str] = set()
    for slug in queue:
        article = articles_by_slug.get(slug)
        if not article or article.get("generated_at", "") < cutoff:
            continue
        tags.update(article.get("tags") or [])
    return tags


def select_candidates(articles: list[dict], queue: dict, limit: int = 3) -> list[dict]:
    """social_scoreが高く、まだキューに無く、直近で似た話題を扱っていない記事を新しい順に選ぶ。
    全記事を対象にしないことで、API呼び出し回数とレビュー量を抑える。"""
    articles_by_slug = {a["slug"]: a for a in articles if a.get("slug")}
    now = datetime.now()
    recent_tags = _recent_queued_tags(queue, articles_by_slug, now)

    selected: list[dict] = []
    used_tags: set[str] = set(recent_tags)
    for article in reversed(articles):
        if len(selected) >= limit:
            break
        slug = article.get("slug")
        if not slug or slug in queue:
            continue
        if social_score(article) < SOCIAL_SCORE_THRESHOLD:
            continue
        article_tags = set(article.get("tags") or [])
        if article_tags and article_tags & used_tags:
            continue  # 直近/今回すでに扱った話題と重複
        selected.append(article)
        used_tags |= article_tags
    return selected


def _validate(data: dict) -> dict:
    angles = data.get("angles")
    if not isinstance(angles, list) or [a.get("type") for a in angles] != list(_REQUIRED_ANGLE_TYPES):
        raise GenerationError(f"angles が4種類そろっていません: {data!r}")
    for angle in angles:
        if not all(k in angle for k in _REQUIRED_ANGLE_KEYS):
            raise GenerationError(f"アングルに必須キーが不足しています: {angle!r}")
        if not isinstance(angle["hook"], str) or not angle["hook"].strip():
            raise GenerationError(f"hookが空です: {angle!r}")
    return data


def generate_for_article(article: dict, client: anthropic.Anthropic) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        headline=article.get("headline", ""),
        tldr=article.get("tldr", ""),
        what_happened=article.get("what_happened", ""),
        why_it_matters=article.get("why_it_matters", ""),
        impact_on_reader=article.get("impact_on_reader", ""),
        risk_point=article.get("risk_point", ""),
        opportunity_point=article.get("opportunity_point", ""),
        url=f"{SITE_BASE_URL}/articles/{article['slug']}.html",
    )
    message = client.messages.create(model=MODEL, max_tokens=4000, messages=[{"role": "user", "content": prompt}])
    text = message.content[0].text.strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GenerationError(f"JSON解析に失敗しました: {text!r}") from exc
    return _validate(data)


def run(limit: int = 3) -> list[str]:
    """未処理の重要記事を探し、SNSコンテンツ+画像を生成してキューに追加する。
    戻り値: 処理したslugのリスト。"""
    import social_visuals

    client = anthropic.Anthropic()
    articles = _load_articles()
    queue = _load_queue()
    candidates = select_candidates(articles, queue, limit=limit)

    processed = []
    for article in candidates:
        slug = article["slug"]
        try:
            result = generate_for_article(article, client)
        except Exception:
            logger.exception("SNSコンテンツ生成に失敗: %s", slug)
            continue

        image_url = article.get("image_url") if article.get("image_kind") == "real" else None
        for angle in result["angles"]:
            try:
                social_visuals.make_hook_slide(image_url, angle["hook"], angle["type"], slug, article.get("source", ""))
                social_visuals.make_carousel_slides(angle["carousel"], angle["type"], slug)
            except Exception:
                logger.exception("画像生成に失敗: %s / %s", slug, angle["type"])
        try:
            social_visuals.make_cta_slide(slug)
        except Exception:
            logger.exception("CTA画像生成に失敗: %s", slug)

        queue[slug] = {
            "headline": article.get("headline", ""),
            "slug": slug,
            "importance_score": article.get("importance_score"),
            "social_score": social_score(article),
            "tags": article.get("tags") or [],
            "generated_at": article.get("generated_at", ""),
            "status": "draft",
            "angles": result["angles"],
        }
        processed.append(slug)
        logger.info("SNSコンテンツ生成成功: %s", slug)

    if processed:
        _save_queue(queue)
    return processed


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    done = run(limit=3)
    print(f"{len(done)}件のSNSコンテンツを生成しました: {done}")
