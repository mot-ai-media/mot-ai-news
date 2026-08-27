"""AI関連ニュースをRSSから収集する。"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

import feedparser

_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE
)

# 検索ワードはここを編集すれば変更できる
JP_QUERY = (
    "生成AI OR ChatGPT OR LLM OR OpenAI OR Anthropic OR Claude OR Gemini OR AIエージェント "
    "OR Copilot OR \"Meta AI\" OR Perplexity OR xAI OR Grok OR DeepSeek OR Mistral OR Sora OR NotebookLM "
    "OR 人工知能 OR 機械学習 OR ディープラーニング OR 基盤モデル OR \"AI規制\""
)
JP_GOOGLE_NEWS_RSS = (
    f"https://news.google.com/rss/search?q={urllib.parse.quote(JP_QUERY)}&hl=ja&gl=JP&ceid=JP:ja"
)
ITMEDIA_AI_RSS = "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"
AINOW_RSS = "https://ainow.ai/feed/"  # AI専門メディア。直リンクなので実画像(og:image)が取れる

# より専門的・技術的なニュースを増やすための追加ソース
HUGGINGFACE_BLOG_RSS = "https://huggingface.co/blog/feed.xml"  # AIモデル/技術の一次情報(英語)
OPENAI_NEWS_RSS = "https://openai.com/news/rss.xml"  # OpenAI公式(英語)
DEEPMIND_BLOG_RSS = "https://deepmind.google/blog/rss.xml"  # Google DeepMind公式(英語)
QIITA_AI_RSS = "https://qiita.com/tags/ai/feed"  # 日本のエンジニアによる技術記事
ZENN_AI_RSS = "https://zenn.dev/topics/ai/feed"  # 日本のエンジニアによる技術記事

# 海外・マニア向けの一次情報/専門メディア(英語)
ARXIV_AI_RSS = "http://export.arxiv.org/rss/cs.AI"  # 論文そのもの。最もマニア向け
MARKTECHPOST_RSS = "https://www.marktechpost.com/feed/"  # AI研究の解説メディア
DECODER_RSS = "https://the-decoder.com/feed/"  # 海外AI専門ニュース
ARSTECHNICA_AI_RSS = "https://arstechnica.com/ai/feed/"  # 大手テックメディアのAI面
TECHCRUNCH_AI_RSS = "https://techcrunch.com/category/artificial-intelligence/feed/"
SIMONWILLISON_RSS = "https://simonwillison.net/atom/everything/"  # 著名LLMエンジニアのブログ(マニア向け)

# フィードを追加/削除したい場合はこのリストを編集する
FEEDS = [
    JP_GOOGLE_NEWS_RSS,
    ITMEDIA_AI_RSS,
    AINOW_RSS,
    HUGGINGFACE_BLOG_RSS,
    OPENAI_NEWS_RSS,
    DEEPMIND_BLOG_RSS,
    QIITA_AI_RSS,
    ZENN_AI_RSS,
    ARXIV_AI_RSS,
    MARKTECHPOST_RSS,
    DECODER_RSS,
    ARSTECHNICA_AI_RSS,
    TECHCRUNCH_AI_RSS,
    SIMONWILLISON_RSS,
]

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Article:
    title: str
    link: str
    summary: str
    source: str
    published: str
    source_domain: str | None = None


def _clean_text(raw: str) -> str:
    text = _TAG_RE.sub("", raw or "")
    return html.unescape(text).strip()


def fetch_candidates(limit_per_feed: int = 15) -> list[Article]:
    """全フィードから記事を取得し、正規化して返す。取得失敗フィードは無視する。"""
    articles: list[Article] = []
    for url in FEEDS:
        try:
            parsed = feedparser.parse(url)
        except Exception:
            continue
        feed_title = getattr(parsed.feed, "title", url)
        for entry in parsed.entries[:limit_per_feed]:
            link = getattr(entry, "link", None)
            title = _clean_text(getattr(entry, "title", ""))
            summary = _clean_text(getattr(entry, "summary", ""))
            published = getattr(entry, "published", "")
            # Google News RSSは<source>に本来の発行元(例: ITmedia)とその実ドメインが入る
            entry_source = getattr(entry, "source", None)
            source = entry_source.get("title") if entry_source else None
            source = source or feed_title
            source_domain = entry_source.get("href") if entry_source else None
            if not source_domain:
                source_domain = urllib.parse.urlsplit(link).netloc or None
            if not link or not title:
                continue
            articles.append(
                Article(
                    title=title,
                    link=link,
                    summary=summary,
                    source=source,
                    published=published,
                    source_domain=source_domain,
                )
            )
    return articles


def filter_unposted(articles: list[Article], posted_links: set[str]) -> list[Article]:
    return [a for a in articles if a.link not in posted_links]


def fetch_og_image(url: str, timeout: int = 8) -> str | None:
    """記事ページのog:imageメタタグだけを軽量に取得する(本文はスクレイピングしない)。"""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        return None
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AiNewsSiteBot/1.0)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            # og:imageは通常<head>内にあるため、先頭部分だけ読めば十分
            chunk = resp.read(65536).decode("utf-8", errors="ignore")
    except Exception:
        return None

    match = _OG_IMAGE_RE.search(chunk)
    return html.unescape(match.group(1)) if match else None
