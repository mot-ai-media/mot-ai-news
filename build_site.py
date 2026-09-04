"""AIニュースまとめサイトのプロトタイプ生成スクリプト。

RSSからAI関連記事を集め、Claudeでキャッチーな見出し・要約を生成し、
静的サイト(output/)として書き出す。

サイト構造(docsフォルダ = GitHub Pagesの公開対象):
  docs/index.html          一覧ページ(最新記事のカード。カードは自サイトの記事ページへリンク)
  docs/articles/<slug>.html  記事ごとの詳細ページ(広告枠あり。下部に元記事へのリンク)
  docs/style.css           共通スタイル

過去に生成した記事メタ情報は articles_data.json に蓄積し、一覧ページは
その蓄積データから最新分を表示する(実行のたびに一覧が全部入れ替わらないようにするため)。

実際のネット公開・広告コードの挿入はここでは行わない(手動で行う)。
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import logging
import re
import urllib.parse
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

import alert
import generator
import goatcounter
import sources
import state

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "docs"  # GitHub Pagesの "/docs" 公開設定に合わせたフォルダ名
ARTICLES_DIR = OUTPUT_DIR / "articles"
TOPICS_DIR = OUTPUT_DIR / "topics"
INDEX_PATH = OUTPUT_DIR / "index.html"
STYLE_PATH = OUTPUT_DIR / "style.css"
SHARE_JS_PATH = OUTPUT_DIR / "share.js"
ABOUT_PATH = OUTPUT_DIR / "about.html"
PRODUCTS_PATH = OUTPUT_DIR / "products.html"
CONTACT_PATH = OUTPUT_DIR / "contact.html"
ROBOTS_PATH = OUTPUT_DIR / "robots.txt"
SITEMAP_PATH = OUTPUT_DIR / "sitemap.xml"
FEED_PATH = OUTPUT_DIR / "feed.xml"
LLMS_TXT_PATH = OUTPUT_DIR / "llms.txt"
MAX_LLMS_TXT_ARTICLES = 200
MIN_TOPIC_ARTICLES = 2  # このタグの記事がこの件数以上あれば、テーマ別ハブページを作る
MAX_FEED_ARTICLES = 30
ARTICLES_DATA_PATH = Path(__file__).parent / "articles_data.json"

MAX_NEW_ARTICLES = 5  # 1回の生成で新規に追加する記事数
MAX_ATTEMPTS_PER_RUN = 15  # 1回の実行で試みるClaude API呼び出しの上限(コスト暴走防止の安全装置)
STALE_ALERT_THRESHOLD = 3  # 何回連続で新規記事0件だったらアラートメールを送るか
ALERT_STATE_PATH = Path(__file__).parent / "alert_state.json"
DIGEST_STATE_PATH = Path(__file__).parent / "digest_state.json"
DIGEST_HOUR_RANGE = (5, 13)  # この時間帯の「その日最初の実行」でだけ日次レポートを送る。
# PCが朝スリープ/電源オフで07:00の定時実行が飛ぶことがあるため、昼過ぎまで幅を持たせて
# 遅れて起動した場合でも送信漏れしないようにしている(9時台までだと丸ごと送信されない事故が起きた)。
MAX_INDEX_ARTICLES = 20  # 一覧ページに表示する件数(蓄積データの中から新しい順)
MAX_STORED_ARTICLES = 1500  # articles_data.jsonに保持する上限(古いものから削除。1日5回更新に合わせて増量)
MAX_RELATED_ARTICLES = 3  # 記事ページ下部に出す関連記事の件数
MAX_INFINITE_SCROLL_ARTICLES = 100  # 一覧ページでスクロール追加読み込みする最大件数

# 本番ドメインが決まったら設定する。空のままだとSNS共有カード・sitemapのURLが不完全になる
SITE_BASE_URL = "https://mot-ai-media.github.io/mot-ai-news"
SITE_SOCIAL_LINKS = ["https://x.com/MOT01AI"]  # 公式X。ハンドル変更時はここも更新すること

# CSP: GitHub PagesはカスタムHTTPヘッダーを設定できないためmetaタグで代用。
# 既存コードがインラインscript/styleに依存しているため'unsafe-inline'を許容(完全な対策ではないが、
# 外部への不正な接続・object-src等は制限する多層防御として機能する)
CSP_META = (
    '<meta http-equiv="Content-Security-Policy" content="'
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://gc.zgo.at; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' https: data:; "
    "connect-src 'self' https://mottainai.goatcounter.com; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-src 'none'"
    '">'
)

# Google Search Console 所有権確認用タグ
GOOGLE_SITE_VERIFICATION = (
    '<meta name="google-site-verification" content="FWf3QNW4wcPX753gENPwai2tBcWBlc-RNTNA1-8tWFI" />'
)

# ダークモード: 描画前にlocalStorageの保存値(無ければOS設定)を見てdata-theme属性を設定する。
# <head>の先頭で同期実行することでチラつき(FOUC)を防ぐ。
THEME_INIT_SCRIPT = (
    "<script>try{var t=localStorage.getItem('mot-theme');"
    "if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches))"
    "{document.documentElement.setAttribute('data-theme','dark');}}catch(e){}</script>"
)

# サブページ(記事/テーマ/about)用の簡易ナビ。トップページのみ検索欄付きの専用ナビを別途持つ
SUB_NAV_TEMPLATE = """<nav class="mot-nav">
  <div class="mot-nav-inner">
    <a class="mot-nav-logo" href="{prefix}index.html">MOT</a>
    <ul class="mot-nav-links" id="mot-nav-menu">
      <li><a href="{prefix}index.html#today">TODAY</a></li>
      <li><a href="{prefix}index.html#latest">LATEST</a></li>
      <li><a href="{prefix}topics/index.html">TOPICS</a></li>
      <li><a href="{prefix}products.html">PRODUCTS</a></li>
      <li><a href="{prefix}contact.html">CONTACT</a></li>
    </ul>
    <div class="mot-nav-actions">
      <button type="button" class="mot-icon-btn" data-theme-toggle aria-label="ダークモード切替">&#9788;</button>
      <button type="button" class="mot-icon-btn mot-nav-hamburger" data-nav-toggle aria-label="メニュー">&#9776;</button>
    </div>
  </div>
</nav>
"""


def _render_sub_nav(prefix: str, page_url: str) -> str:
    return SUB_NAV_TEMPLATE.format(prefix=prefix)

# 見出し・本文用のWebフォント(標準のゴシック体が安っぽく見えるとの指摘を受けて導入)
GOOGLE_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Zen+Kaku+Gothic+New:wght@400;500;700;900"
    "&family=Zen+Old+Mincho:wght@500;700;900"
    '&display=swap" rel="stylesheet">'
)

# GoatCounter(無料アクセス解析)のPVトラッキングスクリプト。空文字にすれば埋め込み無しに戻せる
GOATCOUNTER_SCRIPT = (
    '<script data-goatcounter="https://mottainai.goatcounter.com/count" '
    'async src="//gc.zgo.at/count.js"></script>'
)

# A8.net アフィリエイト広告。空文字にすれば広告非表示に戻せる
_AD_NEW = (
    '<a href="https://px.a8.net/svt/ejp?a8mat=4BC36L+FSKZHU+5J4W+67JU9" rel="sponsored nofollow">'
    '<img border="0" width="336" height="280" alt="" '
    'src="https://www22.a8.net/svt/bgt?aid=260904477955&wid=001&eno=01&mid=s00000025808001043000&mc=1"></a>'
    '<img border="0" width="1" height="1" src="https://www13.a8.net/0.gif?a8mat=4BC36L+FSKZHU+5J4W+67JU9" alt="">'
)
_ADS = [_AD_NEW]


def _pick_ad(entry: dict) -> str:
    """記事ごとに広告を1つだけ表示する(以前は2つ同時表示だったが半分に削減)。
    slugのハッシュで決定的に選ぶので、同じ記事は毎回同じ広告になり、全体ではほぼ半々に分散する。"""
    idx = int(hashlib.sha1(entry.get("slug", "").encode("utf-8")).hexdigest(), 16) % len(_ADS)
    return f'<span class="ad-label">広告</span><div class="ad-item">{_ADS[idx]}</div>'

FAVICON_DATA_URI = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
    "%3Crect width='100' height='100' rx='20' fill='%23000000'/%3E"
    "%3Ctext x='50' y='63' font-size='34' font-family='Arial,sans-serif' font-weight='bold' "
    "fill='white' text-anchor='middle'%3EMOT%3C/text%3E%3C/svg%3E"
)


def _abs_url(path: str) -> str:
    """SITE_BASE_URLが未設定の間は相対パスのまま返す(ローカル確認用)。"""
    if SITE_BASE_URL:
        return f"{SITE_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    return path


def _safe_http_url(url: str | None) -> str | None:
    """http/https以外のスキーム(javascript:等)を弾く。
    外部RSS・スクレイピング結果はそのままhref/srcに埋め込むと危険なため、
    HTMLエスケープとは別にスキーム自体を検証する。"""
    if not url:
        return None
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in ("http", "https"):
        return None
    return url


# 実画像が無い記事の背景グラデーション配色(見出しを白文字で重ねるので暗めに統一)
FALLBACK_GRADIENTS = [
    ("#1a1a2e", "#3a3a68"),
    ("#0f2027", "#2c5364"),
    ("#232526", "#414345"),
    ("#16222a", "#3a6073"),
    ("#302b63", "#0f0c29"),
    ("#1e3c32", "#2d6a4f"),
]


def _pick_gradient(source: str) -> tuple[str, str]:
    palette_index = int(hashlib.md5(source.encode("utf-8")).hexdigest(), 16) % len(FALLBACK_GRADIENTS)
    return FALLBACK_GRADIENTS[palette_index]


STYLE_CSS = """
:root {
  /* 意味を持たせたアクセントカラー(Von Restorff効果: 本当に重要な箇所だけに使う。
     通常のUIはグレー/紺の落ち着いた色で統一し、下記は速報・急上昇・人気・肯定・主要導線にのみ使用) */
  --mot-breaking: #EF4444;
  --mot-trending: #F97316;
  --mot-popular: #F59E0B;
  --mot-positive: #10B981;
  --mot-primary: #2563EB;
  --mot-border: #E2E8F0;
  --mot-text-secondary: #64748B;
}
body {
  font-family: "Zen Kaku Gothic New", "Hiragino Sans", "Yu Gothic", sans-serif;
  background: #f5f6fa;
  color: #222;
  margin: 0;
  padding: 0;
}
main {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px;
}
.card {
  position: relative;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.card-minor {
  opacity: 0.82;
  box-shadow: none;
}
.badge-new {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 2;
  background: var(--mot-breaking);
  color: #fff;
  font-size: 0.7rem;
  font-weight: bold;
  padding: 4px 10px;
  border-radius: 20px;
  letter-spacing: 0.03em;
}
.level-badge {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 8px;
  margin-right: 2px;
}
.level-easy {
  background: #e3f7e8;
  color: #1a8a3f;
}
.level-technical {
  background: #e5edff;
  color: #2955c9;
}
:root[data-theme="dark"] .level-easy {
  background: #16321f;
  color: #4fd97a;
}
:root[data-theme="dark"] .level-technical {
  background: #182645;
  color: #7d9dff;
}
.level-filter {
  display: flex;
  gap: 8px;
  margin: 4px 0 18px;
}
.search-empty {
  color: var(--mot-text-secondary);
  font-size: 0.88rem;
  margin: 4px 0 18px;
}
.level-filter-btn {
  background: #fff;
  border: 1px solid #e5e5ee;
  border-radius: 16px;
  padding: 6px 14px;
  font-size: 0.78rem;
  font-weight: 600;
  color: #555;
  cursor: pointer;
  font-family: inherit;
}
.level-filter-btn.active {
  background: #14141c;
  border-color: #14141c;
  color: #fff;
}
:root[data-theme="dark"] .level-filter-btn {
  background: #17171f;
  border-color: #2a2a35;
  color: #b8b8c8;
}
:root[data-theme="dark"] .level-filter-btn.active {
  background: #e8e8f0;
  color: #0c0c11;
}
.thumb-share {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  display: flex;
  gap: 6px;
}
.thumb-share-btn {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  font-weight: bold;
  text-decoration: none;
  color: #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,0.35);
}
.thumb-share-x {
  background: #000;
}
.thumb-share-line {
  background: #06c755;
  width: auto;
  border-radius: 14px;
  padding: 0 8px;
  font-size: 0.62rem;
  letter-spacing: 0.02em;
}
#scroll-sentinel {
  height: 1px;
}
#load-status {
  text-align: center;
  font-size: 0.8rem;
  color: #999;
  padding: 12px 0;
}
.thumb-link {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background-position: center;
  background-size: cover;
}
.thumb-link .thumb {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-link .thumb.thumb-contain {
  object-fit: contain;
  padding: 14%;
  box-sizing: border-box;
}
.thumb-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-end;
  padding: 16px;
  background: linear-gradient(to top, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0.3) 55%, transparent 100%);
}
.thumb-overlay-text {
  color: #fff;
  font-family: "Zen Old Mincho", serif;
  font-size: 1.15rem;
  font-weight: 700;
  line-height: 1.5;
  text-shadow: 0 1px 4px rgba(0,0,0,0.6);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.card-body {
  padding: 12px 18px 16px;
}
.meta {
  font-size: 0.76rem;
  color: #888;
  margin: 0 0 8px;
}
.summary {
  font-size: 0.85rem;
  line-height: 1.5;
  color: #555;
  margin: 0;
}
.ad-slot {
  margin-top: 10px;
  padding: 6px;
  font-size: 0.7rem;
  color: #bbb;
  border: 1px dashed #ddd;
  text-align: center;
}
.ad-label {
  display: block;
  font-size: 0.65rem;
  color: #bbb;
  margin-bottom: 4px;
  letter-spacing: 0.05em;
}
.ad-item img { max-width: 100%; height: auto; }
footer {
  text-align: center;
  font-size: 0.75rem;
  color: #999;
  padding: 24px;
}
footer a {
  color: #778;
}
.share-buttons {
  display: flex;
  gap: 10px;
  margin: 18px 0;
}
.share-btn {
  flex: 1;
  text-align: center;
  padding: 10px;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: bold;
  text-decoration: none;
  color: #fff;
}
.share-x {
  background: #000;
}
.share-line {
  background: #06c755;
}
.trust-strip {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 0.82rem;
  color: #555;
  margin: 10px 0 18px;
}
.trust-label {
  display: inline-block;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #9a9aab;
  margin-right: 6px;
}
.mot-analysis-label {
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--mot-primary);
  margin: 0 0 8px;
}
.fact-check {
  margin: 16px 0;
  padding: 10px 0 10px 14px;
  border-left: 3px solid var(--mot-border);
}
.fact-check p {
  margin: 6px 0;
  font-size: 0.9rem;
  color: var(--mot-text-secondary);
}
.fact-check cite {
  font-style: normal;
  font-weight: 600;
}
.fact-check footer {
  margin: 0;
}
.tldr {
  padding: 10px 14px;
  border-left: 3px solid var(--mot-primary);
  background: rgba(37, 99, 235, 0.06);
  margin: 0 0 16px;
}
.risk-box, .opportunity-box {
  padding: 10px 14px;
  border-radius: 0 8px 8px 0;
  margin: 16px 0;
}
.risk-box { border-left: 3px solid var(--mot-breaking); background: rgba(239, 68, 68, 0.06); }
.opportunity-box { border-left: 3px solid var(--mot-positive); background: rgba(16, 185, 129, 0.06); }
.risk-box h3, .opportunity-box h3 { margin-top: 0; }
.mot-take-box {
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
  margin: 16px 0;
  border-left: 3px solid var(--mot-primary);
  background: rgba(37, 99, 235, 0.06);
}
.mot-take-box h3 { margin-top: 0; }
:root[data-theme="dark"] .mot-take-box { background: rgba(37, 99, 235, 0.12); }
.watch-next-box {
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
  margin: 16px 0;
  border-left: 3px solid var(--mot-trending);
  background: rgba(249, 115, 22, 0.06);
}
.watch-next-box h3 { margin-top: 0; }
:root[data-theme="dark"] .watch-next-box { background: rgba(249, 115, 22, 0.12); }
.overseas-box, .japan-impact-box {
  padding: 12px 16px;
  border-radius: 0 8px 8px 0;
  margin: 16px 0;
}
.overseas-box { border-left: 3px solid var(--mot-popular); background: rgba(245, 158, 11, 0.06); }
.japan-impact-box { border-left: 3px solid var(--mot-positive); background: rgba(16, 185, 129, 0.06); }
.overseas-box h3, .japan-impact-box h3 { margin-top: 0; }
:root[data-theme="dark"] .overseas-box { background: rgba(245, 158, 11, 0.12); }
:root[data-theme="dark"] .japan-impact-box { background: rgba(16, 185, 129, 0.12); }
.contact-card {
  border: 1px solid var(--mot-border);
  border-radius: 12px;
  padding: 18px 20px;
  margin: 16px 0 28px;
}
.contact-card h2 { margin-top: 0; }
.contact-btn {
  display: inline-block;
  margin-top: 10px;
  padding: 9px 20px;
  border-radius: 999px;
  background: var(--mot-primary);
  color: #fff;
  font-weight: 600;
  font-size: 0.9rem;
  text-decoration: none;
}
.contact-btn:hover { opacity: 0.88; }
:root[data-theme="dark"] .contact-card { border-color: #2a2a36; }
.tag-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 0;
}
.tag-pill {
  display: inline-block;
  padding: 5px 12px;
  border-radius: 16px;
  background: #eef0f5;
  color: #4a4a5e;
  font-size: 0.78rem;
  text-decoration: none;
}
.tag-pill:hover {
  background: #dfe2ea;
}
.tag-pills-large .tag-pill {
  font-size: 0.9rem;
  padding: 8px 16px;
}
.card-tags {
  margin: 10px 0 0;
}
.tag-pill-sm {
  font-size: 0.68rem;
  padding: 3px 9px;
}
.article-faq {
  margin: 24px 0;
  padding-top: 16px;
  border-top: 1px solid #e5e5e5;
}
.article-faq h2 {
  font-size: 1rem;
  margin: 0 0 12px;
}
.faq-item {
  margin-bottom: 14px;
}
.faq-q {
  font-weight: bold;
  font-size: 0.92rem;
  margin: 0 0 4px;
  color: #1a1a2e;
}
.faq-a {
  font-size: 0.88rem;
  color: #444;
  margin: 0;
  line-height: 1.6;
}
.next-insight {
  margin-top: 32px;
  padding-top: 20px;
  border-top: 1px solid #e5e5ee;
}
.insight-list {
  list-style: none;
  padding: 0;
  margin: 14px 0 0;
}
.insight-list li {
  margin-bottom: 8px;
}
.insight-list a {
  color: #14141c;
  font-size: 0.88rem;
  text-decoration: none;
}
.insight-list a:hover {
  text-decoration: underline;
}
.next-up-card {
  display: block;
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  text-decoration: none;
  aspect-ratio: 16 / 8;
  background: #1a1a2e;
}
.next-up-card img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.55;
}
.next-up-headline {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 16px;
  color: #fff;
  font-family: "Zen Old Mincho", serif;
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.5;
  background: linear-gradient(transparent, rgba(0,0,0,0.75));
}
.reactions {
  display: flex;
  gap: 8px;
  margin: 18px 0;
}
.reaction-btn {
  flex: 1;
  padding: 10px 4px;
  border-radius: 8px;
  border: 1px solid #ddd;
  background: #fff;
  font-size: 1.3rem;
  line-height: 1;
  cursor: pointer;
  transition: transform 0.12s, background 0.12s, border-color 0.12s;
}
.reaction-btn:hover {
  background: #f7f7f7;
}
.reaction-btn.active {
  background: #fff3cd;
  border-color: #ffcc00;
  transform: scale(1.08);
}

/* 記事詳細ページ用 */
.article-page main {
  max-width: 640px;
}
.article-page .thumb-link {
  border-radius: 12px;
  margin-bottom: 16px;
  pointer-events: none; /* 記事ページ内では画像はリンクにしない */
}
.article-page h1.headline {
  font-family: "Zen Old Mincho", serif;
  font-weight: 700;
  font-size: 1.5rem;
  line-height: 1.6;
  margin: 0 0 8px;
}
.article-page .summary {
  font-size: 1.05rem;
  line-height: 1.9;
  letter-spacing: 0.02em;
  color: #2b2b33;
  margin-bottom: 20px;
}
.article-page .summary p {
  margin: 0 0 20px;
}
.article-page .summary p:last-child {
  margin-bottom: 0;
}
.ad-slot-large {
  margin: 20px 0;
  padding: 24px;
  font-size: 0.8rem;
  color: #bbb;
  border: 1px dashed #ddd;
  text-align: center;
  border-radius: 8px;
}
.source-link {
  display: inline-block;
  margin-top: 8px;
  padding: 10px 18px;
  background: var(--mot-primary);
  color: #fff;
  text-decoration: none;
  border-radius: 6px;
  font-size: 0.9rem;
}
.source-link:hover {
  background: #1d4ed8;
}
.back-link {
  display: inline-block;
  margin-bottom: 16px;
  color: #667;
  font-size: 0.85rem;
  text-decoration: none;
}

/* サイト共有・リンクコピー(トースト通知) */
.site-share-btn {
  margin-top: 10px;
  padding: 7px 16px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.35);
  background: transparent;
  color: #fff;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
}
.share-copy-btn {
  cursor: pointer;
  border: none;
  font-family: inherit;
  background: #667;
}
.share-native-btn {
  display: none;
  cursor: pointer;
  border: none;
  font-family: inherit;
  background: #1a1a2e;
}
.toast {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%) translateY(20px);
  background: rgba(26,26,46,0.92);
  color: #fff;
  padding: 10px 18px;
  border-radius: 20px;
  font-size: 0.82rem;
  opacity: 0;
  transition: opacity 0.25s, transform 0.25s;
  z-index: 100;
  pointer-events: none;
  white-space: nowrap;
}
.toast.show {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

/* ランキングセクション */
.section-heading {
  font-size: 0.88rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  margin: 4px 0 14px;
  color: #4a4a5e;
}
/* ============ ここから: トップページ全面刷新 ============ */

/* --- ダークモード(海外プロダクト風、純黒ではなく少し青みのある黒) --- */
:root[data-theme="dark"] body { background: #0c0c11; color: #dcdce6; }
:root[data-theme="dark"] .mot-nav { background: #000; }
:root[data-theme="dark"] .card,
:root[data-theme="dark"] .today-card,
:root[data-theme="dark"] .article-faq,
:root[data-theme="dark"] .reaction-btn {
  background: #17171f;
  border-color: #2a2a35;
  box-shadow: none;
}
:root[data-theme="dark"] .summary,
:root[data-theme="dark"] .today-facts dd,
:root[data-theme="dark"] .hero-why { color: #b8b8c8; }
:root[data-theme="dark"] .meta,
:root[data-theme="dark"] .hero-meta { color: #8a8a9a; }
:root[data-theme="dark"] .hero-headline,
:root[data-theme="dark"] .section-title-lg,
:root[data-theme="dark"] .today-card-title,
:root[data-theme="dark"] h1.headline { color: #f0f0f6; }
:root[data-theme="dark"] .hero { border-color: #24242e; }
:root[data-theme="dark"] .fact-what { border-left-color: #3a3f7a; }
:root[data-theme="dark"] .fact-why { border-left-color: #6b551f; }
:root[data-theme="dark"] .fact-impact { border-left-color: #1f5c47; }
:root[data-theme="dark"] .fact-what dt { color: #8fa0ff; }
:root[data-theme="dark"] .fact-why dt { color: #f0b649; }
:root[data-theme="dark"] .fact-impact dt { color: #3ecda0; }
:root[data-theme="dark"] .ad-slot,
:root[data-theme="dark"] .ad-slot-large,
:root[data-theme="dark"] .topic-tile { border-color: #2a2a35; color: #77778a; }
:root[data-theme="dark"] .topic-tile { background: #17171f; color: #cfcfe0; }
:root[data-theme="dark"] .tag-pill { background: #1e1e29; color: #b8b8cc; }
:root[data-theme="dark"] .next-insight { border-color: #2a2a35; }
:root[data-theme="dark"] .back-link,
:root[data-theme="dark"] .insight-list a { color: #9494a8; }
:root[data-theme="dark"] .trust-strip { color: #a0a0b4; }
:root[data-theme="dark"] .source-link { background: #3b6fe0; }
:root[data-theme="dark"] .mot-tagline-strip,
:root[data-theme="dark"] .footer-share-btn,
:root[data-theme="dark"] footer { color: #74748a; }
:root[data-theme="dark"] footer a { color: #9494c0; }

/* --- ナビゲーションヘッダー --- */
.mot-nav {
  background: #0d0d12;
  color: #fff;
  position: sticky;
  top: 0;
  z-index: 50;
}
.mot-nav-inner {
  max-width: 960px;
  margin: 0 auto;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 24px;
  position: relative;
}
.mot-nav-logo {
  font-family: "Zen Kaku Gothic New", sans-serif;
  font-weight: 900;
  font-size: 1.05rem;
  color: #fff;
  text-decoration: none;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
.mot-nav-links {
  list-style: none;
  display: flex;
  gap: 20px;
  margin: 0;
  padding: 0;
  flex: 1;
}
.mot-nav-links a {
  color: #a8a8ba;
  text-decoration: none;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.mot-nav-links a:hover { color: #fff; }
.mot-nav-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mot-search-input {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.16);
  border-radius: 20px;
  padding: 6px 14px;
  color: #fff;
  font-size: 0.78rem;
  width: 120px;
  font-family: inherit;
}
.mot-search-input::placeholder { color: #82829a; }
.mot-icon-btn {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.22);
  color: #fff;
  border-radius: 50%;
  width: 36px;
  height: 36px;
  cursor: pointer;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.mot-nav-hamburger { display: none; }
@media (max-width: 780px) {
  .mot-nav-links {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: #0d0d12;
    flex-direction: column;
    padding: 8px 16px 14px;
    gap: 2px;
  }
  .mot-nav-links.open { display: flex; }
  .mot-nav-links a {
    padding: 10px 0;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  .mot-nav-hamburger { display: flex; }
  .mot-search-input { width: 76px; }
}

.mot-main {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 16px;
}
.mot-tagline-strip {
  text-align: center;
  font-size: 0.76rem;
  color: #9a9aab;
  padding: 14px 16px 0;
  margin: 0;
}
.footer-share-btn {
  background: none;
  border: none;
  color: #778;
  font-size: 0.75rem;
  cursor: pointer;
  font-family: inherit;
  text-decoration: underline;
  padding: 0;
  margin-top: 10px;
}
/* --- CONTINUE EXPLORING(JSが該当時のみ挿入) --- */
.continue-exploring {
  margin-bottom: 28px;
}
.continue-card {
  display: block;
  padding: 14px 18px;
  background: #f3f1ff;
  border: 1px solid #ded8ff;
  border-radius: 10px;
  color: #4a3fc0;
  text-decoration: none;
  font-size: 0.88rem;
  font-weight: 600;
}
.continue-card:hover { border-color: #b8adff; }
:root[data-theme="dark"] .continue-card {
  background: #1c1a2e;
  border-color: #332f52;
  color: #b0a4ff;
}

/* --- 注目ニュースティッカー(タイトル直下、自動スクロール+手動でも自由に前後できる) --- */
.mot-ticker {
  overflow-x: auto;
  overflow-y: hidden;
  margin: 14px 0 0;
  -webkit-mask-image: linear-gradient(to right, transparent, black 6%, black 94%, transparent);
  mask-image: linear-gradient(to right, transparent, black 6%, black 94%, transparent);
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.mot-ticker::-webkit-scrollbar { display: none; }
.mot-ticker-track {
  display: flex;
  gap: 10px;
  width: max-content;
  padding: 0 16px;
}
.mot-ticker-item {
  position: relative;
  flex-shrink: 0;
  width: 340px;
  height: 191px;
  border-radius: 10px;
  overflow: hidden;
  background-size: cover;
  background-position: center;
  text-decoration: none;
  display: flex;
  align-items: flex-end;
}
.mot-ticker-item::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.15) 60%, transparent 100%);
}
.mot-ticker-text {
  position: relative;
  z-index: 1;
  color: rgba(255,255,255,0.88);
  font-size: 0.88rem;
  font-weight: 600;
  line-height: 1.45;
  padding: 10px;
}
@media (max-width: 600px) {
  .mot-ticker-item {
    width: 240px;
    height: 135px;
  }
  .mot-ticker-text {
    font-size: 0.76rem;
  }
}
/* --- HERO --- */
.hero {
  padding: 36px 0 28px;
  border-bottom: 1px solid #e5e5ee;
  margin-bottom: 36px;
}
.hero-label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: #9a9aab;
  margin: 0 0 14px;
}
.hero-link { text-decoration: none; }
.hero-headline {
  font-family: "Zen Old Mincho", serif;
  font-weight: 900;
  font-size: 1.9rem;
  line-height: 1.45;
  color: #14141c;
  margin: 0 0 16px;
}
.hero-link:hover .hero-headline { text-decoration: underline; }
.hero-why {
  font-size: 1rem;
  color: #555;
  margin: 0 0 14px;
  line-height: 1.7;
}
.hero-meta { font-size: 0.78rem; color: #999; }
.hero-meta .dot { margin: 0 6px; }
@media (max-width: 600px) {
  .hero-headline { font-size: 1.4rem; }
}

/* --- セクション共通 --- */
.section-label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: #9a9aab;
  margin: 0 0 6px;
}
.section-title-lg {
  font-family: "Zen Old Mincho", serif;
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0 0 22px;
  color: #14141c;
}

/* --- TODAY IN AI --- */
.today-ai { margin-bottom: 44px; }
.today-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}
.today-card {
  background: #fff;
  border: 1px solid #e5e5ee;
  border-left: 3px solid #7c8cff;
  border-radius: 12px;
  padding: 18px;
}
.today-card-title {
  display: block;
  font-weight: 700;
  font-size: 0.92rem;
  color: #14141c;
  text-decoration: none;
  margin-bottom: 14px;
  line-height: 1.55;
}
.today-card-title:hover { text-decoration: underline; }
.today-card-major {
  border-left-color: var(--mot-primary);
  border-left-width: 4px;
  background: rgba(37, 99, 235, 0.04);
}
.today-facts { margin: 0; }
.today-facts div {
  margin-bottom: 10px;
  padding-left: 10px;
  border-left: 2px solid #eceef3;
}
.today-facts div:last-child { margin-bottom: 0; }
.today-facts dt {
  font-size: 0.63rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  margin: 0 0 2px;
}
.today-facts dd {
  margin: 0;
  font-size: 0.83rem;
  color: #444;
  line-height: 1.55;
}
.fact-what dt { color: #5b7fff; }
.fact-what { border-left-color: #c7cfff; }
.fact-why dt { color: #d98a1f; }
.fact-why { border-left-color: #f2d9ae; }
.fact-impact dt { color: #21a17a; }
.fact-impact { border-left-color: #b7e5d6; }

/* --- TOPICS探索 --- */
.topics-explore { margin-bottom: 44px; }
.topics-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.topic-tile {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 24px;
  border: 1px solid #e5e5ee;
  background: #fff;
  color: #2a2a3a;
  text-decoration: none;
  font-size: 0.85rem;
  font-weight: 600;
  transition: border-color 0.15s, transform 0.15s;
}
.topic-tile:hover {
  border-color: var(--mot-primary);
  transform: translateY(-1px);
}
.topic-count {
  font-size: 0.7rem;
  color: #9a9aab;
  font-weight: 400;
}

/* --- LATEST NEWS(既存カード一覧) --- */
.latest-news { margin-bottom: 20px; }
"""

SHARE_JS = """(function () {
  function showToast(msg) {
    var toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = msg;
    document.body.appendChild(toast);
    requestAnimationFrame(function () {
      toast.classList.add("show");
    });
    setTimeout(function () {
      toast.classList.remove("show");
      setTimeout(function () {
        toast.remove();
      }, 300);
    }, 1800);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
    } catch (e) {}
    document.body.removeChild(ta);
    return Promise.resolve();
  }

  document.addEventListener("click", function (e) {
    var copyBtn = e.target.closest("[data-copy-url]");
    if (copyBtn) {
      copyText(copyBtn.getAttribute("data-copy-url")).then(function () {
        showToast("リンクをコピーしました");
      });
      return;
    }
    var shareBtn = e.target.closest("[data-native-share]");
    if (shareBtn) {
      var url = shareBtn.getAttribute("data-share-url");
      var title = shareBtn.getAttribute("data-share-title");
      if (navigator.share) {
        navigator.share({ title: title, url: url }).catch(function () {});
      } else {
        copyText(url).then(function () {
          showToast("リンクをコピーしました");
        });
      }
    }
  });

  document.querySelectorAll("[data-native-share-only]").forEach(function (el) {
    if (navigator.share) {
      el.style.display = "block";
    }
  });

  // ダークモード切り替え(<head>のtheme_initが初期状態は既に設定済み。ここではトグル操作のみ扱う)
  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var isDark = document.documentElement.getAttribute("data-theme") === "dark";
      if (isDark) {
        document.documentElement.removeAttribute("data-theme");
        try { localStorage.setItem("mot-theme", "light"); } catch (e) {}
      } else {
        document.documentElement.setAttribute("data-theme", "dark");
        try { localStorage.setItem("mot-theme", "dark"); } catch (e) {}
      }
    });
  });

  // サイト内検索 + 難易度フィルター(記事カードの絞り込み。クライアントサイドのみ、外部送信なし)
  var searchInput = document.getElementById("mot-search");
  var levelFilter = document.getElementById("level-filter");
  var searchEmpty = document.getElementById("search-empty");
  var currentLevel = "all";

  function applyCardFilters() {
    var q = searchInput ? searchInput.value.trim().toLowerCase() : "";
    // 検索語がある時は、まだ無限スクロールで読み込まれていない記事も先に全部読み込んでから
    // 絞り込む(そうしないと「表示済みの20件」しか検索対象にならず、無反応に見えてしまうため)
    if (q && window.motLoadAllCards) {
      window.motLoadAllCards();
    }
    var visibleCount = 0;
    document.querySelectorAll("[data-searchable]").forEach(function (card) {
      var text = (card.getAttribute("data-search-text") || "").toLowerCase();
      var matchesSearch = !q || text.indexOf(q) !== -1;
      var matchesLevel = currentLevel === "all" || card.getAttribute("data-level") === currentLevel;
      var visible = matchesSearch && matchesLevel;
      card.style.display = visible ? "" : "none";
      if (visible) visibleCount++;
    });
    if (searchEmpty) {
      searchEmpty.style.display = (q || currentLevel !== "all") && visibleCount === 0 ? "block" : "none";
    }

    // 検索中は上部(ティッカー/HERO/TODAY'S BRIEFING/TOPICS等)を隠し、検索結果だけに集中できるようにする
    document.querySelectorAll(".mot-tagline-strip, .mot-ticker, #continue-exploring, .hero, .today-ai, .topics-explore")
      .forEach(function (el) { el.style.display = q ? "none" : ""; });
    var resultsHeading = document.querySelector(".latest-news .section-title-lg");
    if (resultsHeading) {
      resultsHeading.textContent = q ? "検索結果" : "すべてのニュース";
    }
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyCardFilters);
  }
  if (levelFilter) {
    levelFilter.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-filter-level]");
      if (!btn) return;
      currentLevel = btn.getAttribute("data-filter-level");
      levelFilter.querySelectorAll(".level-filter-btn").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      applyCardFilters();
    });
  }

  // モバイルナビの開閉
  var navToggle = document.querySelector("[data-nav-toggle]");
  var navMenu = document.getElementById("mot-nav-menu");
  if (navToggle && navMenu) {
    navToggle.addEventListener("click", function () {
      navMenu.classList.toggle("open");
    });
  }

  // 注目ニュースティッカー: 自動でゆっくり流しつつ、ユーザーがドラッグ/スワイプ/ホイールで
  // いつでも自由に前後にスクロールできるようにする(操作したら一時停止し、少し経ったら再開)
  var ticker = document.querySelector(".mot-ticker");
  if (ticker) {
    var tickerTrack = ticker.querySelector(".mot-ticker-track");
    var prefersReducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var tickerAuto = !prefersReducedMotion;
    var tickerResumeTimer = null;

    function pauseTickerAuto() {
      tickerAuto = false;
      if (tickerResumeTimer) clearTimeout(tickerResumeTimer);
      tickerResumeTimer = setTimeout(function () { tickerAuto = true; }, 2500);
    }
    ["pointerdown", "wheel", "touchstart"].forEach(function (evt) {
      ticker.addEventListener(evt, pauseTickerAuto, { passive: true });
    });

    if (!prefersReducedMotion && tickerTrack) {
      (function tickerTick() {
        if (tickerAuto) {
          var half = tickerTrack.scrollWidth / 2;
          if (half > 0) {
            ticker.scrollLeft += 0.5;
            if (ticker.scrollLeft >= half) {
              ticker.scrollLeft -= half;
            }
          }
        }
        requestAnimationFrame(tickerTick);
      })();
    }
  }

  // CONTINUE EXPLORING: 閲覧したタグをこの端末のlocalStorageにだけ記録する(サーバー送信なし)。
  // トップページでは、その記録と実際の最新記事日時を比べて「本当に新しい記事がある場合だけ」案内する
  // (架空の緊急性・偽の新着表示は作らない)。
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function localStamp(d) {
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) + " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }

  if (window.motPageTags && window.motPageTags.length) {
    try {
      var now = localStamp(new Date());
      var visited = JSON.parse(localStorage.getItem("mot-visited-tags") || "[]");
      visited = visited.filter(function (v) { return window.motPageTags.indexOf(v.tag) === -1; });
      window.motPageTags.forEach(function (t) { visited.unshift({ tag: t, at: now }); });
      localStorage.setItem("mot-visited-tags", JSON.stringify(visited.slice(0, 8)));
    } catch (e) {}
  }

  var topicsDataEl = document.getElementById("topics-summary-data");
  var continueMount = document.getElementById("continue-exploring");
  if (topicsDataEl && continueMount) {
    try {
      var topics = JSON.parse(topicsDataEl.textContent || "{}");
      var visitedTags = JSON.parse(localStorage.getItem("mot-visited-tags") || "[]");
      for (var i = 0; i < visitedTags.length; i++) {
        var v = visitedTags[i];
        var t = topics[v.tag];
        if (t && t.latest && t.latest > v.at) {
          var section = document.createElement("section");
          section.className = "continue-exploring";
          var label = document.createElement("p");
          label.className = "section-label";
          label.textContent = "CONTINUE EXPLORING";
          var link = document.createElement("a");
          link.className = "continue-card";
          link.href = "topics/" + t.slug + ".html";
          link.textContent = "前回見ていた「#" + v.tag + "」に新しいニュースがあります →";
          section.appendChild(label);
          section.appendChild(link);
          continueMount.appendChild(section);
          break;
        }
      }
    } catch (e) {}
  }
})();
"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{theme_init}
{csp}
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI特化メディアMOT | 生成AI・ChatGPT・Claude最新ニュースまとめ</title>
<meta name="description" content="ChatGPT・Claude・Geminiなど生成AIの最新ニュースを毎日更新。新機能・料金・使い方まで、AI業界の動きを分かりやすくまとめてお届けします。">
<link rel="canonical" href="{page_url}">
{google_verification}
<link rel="alternate" type="application/rss+xml" title="AI特化メディアMOT" href="feed.xml">
<link rel="icon" href="{favicon}">
{google_font}
<link rel="stylesheet" href="style.css">
<script defer src="share.js"></script>
{goatcounter}
<meta property="og:type" content="website">
<meta property="og:site_name" content="AI特化メディアMOT">
<meta property="og:title" content="AI特化メディアMOT">
<meta property="og:description" content="生成AI・LLM関連の最新ニュースをキャッチーな見出しでまとめてお届け">
<meta property="og:image" content="{site_logo}">
<meta property="og:url" content="{page_url}">
<meta name="twitter:card" content="summary">
<meta name="twitter:image" content="{site_logo}">
{organization_jsonld}
</head>
<body>
<nav class="mot-nav">
  <div class="mot-nav-inner">
    <a class="mot-nav-logo" href="index.html">MOT</a>
    <ul class="mot-nav-links" id="mot-nav-menu">
      <li><a href="#today">TODAY</a></li>
      <li><a href="#latest">LATEST</a></li>
      <li><a href="topics/index.html">TOPICS</a></li>
      <li><a href="products.html">PRODUCTS</a></li>
      <li><a href="contact.html">CONTACT</a></li>
    </ul>
    <div class="mot-nav-actions">
      <input id="mot-search" class="mot-search-input" type="text" placeholder="検索" aria-label="記事を検索">
      <button type="button" class="mot-icon-btn" data-theme-toggle aria-label="ダークモード切替">&#9788;</button>
      <button type="button" class="mot-icon-btn mot-nav-hamburger" data-nav-toggle aria-label="メニュー">&#9776;</button>
    </div>
  </div>
</nav>
<p class="mot-tagline-strip">進化するAIの「今」に、もっと早くアクセス。／最終更新: {generated_at}</p>
{ticker}
<main class="mot-main">
<div id="continue-exploring"></div>
{hero}
{todays_briefing}
{topics_explore}
<section class="latest-news" id="latest">
  <p class="section-label">LATEST NEWS</p>
  <h2 class="section-title-lg">すべてのニュース</h2>
  <div class="level-filter" id="level-filter" role="group" aria-label="難易度で絞り込み">
    <button type="button" class="level-filter-btn active" data-filter-level="all">すべて</button>
    <button type="button" class="level-filter-btn" data-filter-level="easy">&#128994; やさしい</button>
    <button type="button" class="level-filter-btn" data-filter-level="technical">&#128309; テクニカル</button>
  </div>
  <p id="search-empty" class="search-empty" style="display:none;">条件に一致する記事が見つかりませんでした。</p>
  {cards}
  <div id="scroll-sentinel"></div>
  <p id="load-status"></p>
</section>
</main>
<footer>
  各記事の詳細・引用元は見出しのリンク先をご確認ください。<br>
  <a href="topics/index.html">テーマ別まとめ</a>　|　<a href="feed.xml">RSSフィード</a>　|　<a href="about.html">運営者情報・プライバシーポリシー</a><br>
  <button type="button" class="footer-share-btn" data-native-share data-share-url="{page_url}" data-share-title="AI特化メディアMOT">&#8599; サイトをシェア</button>
</footer>
<script type="application/json" id="more-articles-data">{more_articles_json}</script>
<script type="application/json" id="topics-summary-data">{topics_summary_json}</script>
<script>
(function() {{
  var dataEl = document.getElementById("more-articles-data");
  var queue = JSON.parse(dataEl.textContent || "[]");
  var main = document.querySelector(".latest-news");
  var sentinel = document.getElementById("scroll-sentinel");
  var status = document.getElementById("load-status");
  var BATCH = 8;

  function renderCard(item) {{
    var article = document.createElement("article");
    article.className = item.importance === "minor" ? "card card-minor" : "card";
    article.setAttribute("data-searchable", "");
    article.setAttribute("data-search-text", item.headline);
    article.setAttribute("data-level", item.level);

    if (item.is_new) {{
      var badge = document.createElement("span");
      badge.className = "badge-new";
      badge.textContent = "NEW";
      article.appendChild(badge);
    }}

    var thumbLink = document.createElement("a");
    thumbLink.className = "thumb-link";
    thumbLink.href = "articles/" + item.slug + ".html";
    if (item.image_kind === "real" && item.image_url) {{
      var img = document.createElement("img");
      img.className = "thumb";
      img.loading = "lazy";
      img.alt = "";
      img.src = item.image_url;
      thumbLink.appendChild(img);
    }} else if (item.g1 && item.g2) {{
      thumbLink.style.background = "linear-gradient(135deg, " + item.g1 + ", " + item.g2 + ")";
    }}
    var overlay = document.createElement("div");
    overlay.className = "thumb-overlay";
    var overlayText = document.createElement("span");
    overlayText.className = "thumb-overlay-text";
    overlayText.textContent = item.headline;
    overlay.appendChild(overlayText);
    thumbLink.appendChild(overlay);
    article.appendChild(thumbLink);

    var thumbShare = document.createElement("div");
    thumbShare.className = "thumb-share";
    var shareX = document.createElement("a");
    shareX.className = "thumb-share-btn thumb-share-x";
    shareX.href = "https://twitter.com/intent/tweet?text=" + item.share_text + "&url=" + item.share_url;
    shareX.target = "_blank";
    shareX.rel = "noopener noreferrer";
    shareX.setAttribute("aria-label", "Xで共有");
    shareX.innerHTML = {icon_x_svg_js};
    shareX.addEventListener("click", function(e) {{ e.stopPropagation(); }});
    thumbShare.appendChild(shareX);
    var shareLine = document.createElement("a");
    shareLine.className = "thumb-share-btn thumb-share-line";
    shareLine.href = "https://social-plugins.line.me/lineit/share?url=" + item.share_url + "&text=" + item.share_text;
    shareLine.target = "_blank";
    shareLine.rel = "noopener noreferrer";
    shareLine.setAttribute("aria-label", "LINEで共有");
    shareLine.textContent = "LINE";
    shareLine.addEventListener("click", function(e) {{ e.stopPropagation(); }});
    thumbShare.appendChild(shareLine);
    article.appendChild(thumbShare);

    var body = document.createElement("div");
    body.className = "card-body";

    var h2 = document.createElement("h2");
    h2.className = "sr-only";
    var titleLink = document.createElement("a");
    titleLink.href = "articles/" + item.slug + ".html";
    titleLink.textContent = item.headline;
    h2.appendChild(titleLink);
    body.appendChild(h2);

    var meta = document.createElement("p");
    meta.className = "meta";
    var levelIcon = item.level === "technical" ? "🔵" : "🟢";
    meta.textContent = levelIcon + " " + item.level_label + " ・出典: " + item.source + "　·　" + item.reading_time + "分で読める";
    body.appendChild(meta);

    var summary = document.createElement("p");
    summary.className = "summary";
    summary.textContent = item.summary;
    body.appendChild(summary);

    if (item.tags && item.tags.length) {{
      var tagWrap = document.createElement("div");
      tagWrap.className = "tag-pills card-tags";
      item.tags.slice(0, 3).forEach(function (t) {{
        var chip = document.createElement("span");
        chip.className = "tag-pill tag-pill-sm";
        chip.textContent = "#" + t;
        tagWrap.appendChild(chip);
      }});
      body.appendChild(tagWrap);
    }}

    var adSlot = document.createElement("div");
    adSlot.className = "ad-slot";
    adSlot.innerHTML = item.ad_code;
    body.appendChild(adSlot);

    article.appendChild(body);
    return article;
  }}

  function loadMore() {{
    if (queue.length === 0) {{
      status.textContent = "すべての記事を表示しました";
      observer.disconnect();
      return;
    }}
    var batch = queue.splice(0, BATCH);
    batch.forEach(function(item) {{
      main.insertBefore(renderCard(item), sentinel);
    }});
  }}

  var observer = new IntersectionObserver(function(entries) {{
    if (entries[0].isIntersecting) {{
      loadMore();
    }}
  }});
  observer.observe(sentinel);

  // 検索が「表示済みの記事だけ」を対象にして機能してないように見えるのを防ぐため、
  // 検索時にはこれを呼んで残り全件を先に読み込ませる(share.jsから呼ばれる)
  window.motLoadAllCards = function() {{
    while (queue.length > 0) {{
      loadMore();
    }}
  }};
}})();
</script>
</body>
</html>
"""

# Xの共有ボタン用アイコン(公式ロゴの形をSVGで再現。外部画像は使わずCSPにも影響しない)。
# LINEは文字ロゴ("LINE"のテキスト表示)の方が分かりやすいため、SVGではなくテキストにしている
ICON_X_SVG = (
    '<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true">'
    '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835'
    'L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>'
)

THUMB_SHARE_TEMPLATE = (
    '<div class="thumb-share">'
    '<a class="thumb-share-btn thumb-share-x" href="https://twitter.com/intent/tweet?text={share_text}&url={share_url}" '
    f'target="_blank" rel="noopener noreferrer" aria-label="Xで共有" onclick="event.stopPropagation()">{ICON_X_SVG}</a>'
    '<a class="thumb-share-btn thumb-share-line" href="https://social-plugins.line.me/lineit/share?url={share_url}&text={share_text}" '
    'target="_blank" rel="noopener noreferrer" aria-label="LINEで共有" onclick="event.stopPropagation()">LINE</a>'
    "</div>"
)


def _thumb_share_html(slug: str, headline: str) -> str:
    page_url = _abs_url(f"articles/{slug}.html")
    return THUMB_SHARE_TEMPLATE.format(
        share_text=urllib.parse.quote(headline),
        share_url=urllib.parse.quote(page_url),
    )


CARD_TEMPLATE = """<article class="card{importance_class}" data-searchable data-search-text="{search_text}" data-level="{level}">
  {new_badge}{thumbnail}{thumb_share}
  <div class="card-body">
    <h2 class="sr-only"><a href="articles/{slug}.html">{headline}</a></h2>
    <p class="meta">{level_badge} 出典: {source}　&middot;　{reading_time}分で読める</p>
    <p class="summary">{summary}</p>
    {card_tags}
    <div class="ad-slot">{ad_code}</div>
  </div>
</article>
"""

NEW_BADGE_HTML = '<span class="badge-new">NEW</span>'
NEW_BADGE_HOURS = 5  # この時間以内に生成された記事にNEWバッジを付ける(1日5回更新運用に合わせた間隔)

ARTICLE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{theme_init}
{csp}
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{seo_title} | AI特化メディアMOT</title>
<meta name="description" content="{summary}">
<link rel="canonical" href="{page_url}">
<link rel="icon" href="{favicon}">
{google_font}
<link rel="stylesheet" href="../style.css">
<script defer src="../share.js"></script>
{goatcounter}
<meta property="og:type" content="article">
<meta property="og:site_name" content="AI特化メディアMOT">
<meta property="og:title" content="{headline}">
<meta property="og:description" content="{summary}">
<meta property="og:image" content="{og_image}">
<meta property="og:url" content="{page_url}">
<meta property="article:published_time" content="{iso_published}">
<meta property="article:modified_time" content="{iso_published}">
<meta name="twitter:card" content="summary_large_image">
{structured_data}
</head>
<body class="article-page">
{nav}
<main>
  <a class="back-link" href="../index.html">&laquo; 一覧に戻る</a>
  {thumbnail}
  <h1 class="headline">{headline}</h1>
  <div class="trust-strip">
    <span>{level_badge}</span>
    <span><span class="trust-label">SOURCE</span>{source}</span>
    <span><span class="trust-label">UPDATED</span>{generated_at}</span>
  </div>
  <p class="mot-analysis-label">MOT ANALYSIS</p>
  <div class="summary">{body}</div>
  {tags}
  {tag_tracker}
  <div class="ad-slot-large">{ad_code}</div>
  <blockquote class="fact-check" cite="{link}">
    <span class="trust-label">FACT</span>
    <p>本記事は<cite>{source}</cite>の報道をもとに、MOT編集部が独自の視点で要約・解説したものです。</p>
    <footer><a class="source-link" href="{link}" target="_blank" rel="noopener noreferrer">元記事（<cite>{source}</cite>）を読む &rarr;</a></footer>
  </blockquote>
  {faq}
  <div class="share-buttons">
    <a class="share-btn share-x" href="https://twitter.com/intent/tweet?text={share_text}&url={share_url}" target="_blank" rel="noopener noreferrer">Xで共有</a>
    <a class="share-btn share-line" href="https://social-plugins.line.me/lineit/share?url={share_url}&text={share_text}" target="_blank" rel="noopener noreferrer">LINEで共有</a>
    <button type="button" class="share-btn share-copy-btn" data-copy-url="{page_url}">リンクをコピー</button>
    <button type="button" class="share-btn share-native-btn" data-native-share data-native-share-only data-share-url="{page_url}" data-share-title="{headline}">共有</button>
  </div>
  <div class="reactions" id="reactions" data-slug="{slug}">
    <button type="button" class="reaction-btn" data-emoji="like">&#128077;</button>
    <button type="button" class="reaction-btn" data-emoji="surprised">&#128558;</button>
    <button type="button" class="reaction-btn" data-emoji="sad">&#128546;</button>
    <button type="button" class="reaction-btn" data-emoji="fire">&#128293;</button>
  </div>
  {next_insight}
</main>
<footer>
  この要約はAIが元記事をもとに作成したものです。詳細は元記事をご確認ください。<br>
  <a href="../about.html">運営者情報・プライバシーポリシー</a>
</footer>
<script>
(function() {{
  var box = document.getElementById("reactions");
  var slug = box.getAttribute("data-slug");
  var key = "reaction_" + slug;
  var saved = null;
  try {{ saved = localStorage.getItem(key); }} catch (e) {{}}

  var buttons = box.querySelectorAll(".reaction-btn");
  buttons.forEach(function(btn) {{
    if (btn.getAttribute("data-emoji") === saved) {{
      btn.classList.add("active");
    }}
    btn.addEventListener("click", function() {{
      var isActive = btn.classList.contains("active");
      buttons.forEach(function(b) {{ b.classList.remove("active"); }});
      try {{
        if (isActive) {{
          localStorage.removeItem(key);
        }} else {{
          btn.classList.add("active");
          localStorage.setItem(key, btn.getAttribute("data-emoji"));
        }}
      }} catch (e) {{}}
    }});
  }});
}})();
</script>
</body>
</html>
"""

NEXT_INSIGHT_TEMPLATE = """<section class="next-insight">
  <p class="section-label">NEXT INSIGHT</p>
  <h2 class="section-title-lg">このニュースを理解したら、次に知りたいこと</h2>
  <a class="next-up-card" href="{slug}.html">
    {image_tag}
    <span class="next-up-headline">{headline}</span>
  </a>
{items}</section>"""

RELATED_ITEM_TEMPLATE = '  <li><a href="{slug}.html">{headline}</a></li>'

def _pick_editorial_highlights(articles_data: list[dict], limit: int = 3) -> list[dict]:
    """PVデータが無い間の暫定表示。「人気」を偽装しないよう、閲覧数ではなく
    記事の情報の厚み(実画像・FAQの有無・本文の長さ)から機械的に選ぶ。"""
    def score(e: dict) -> tuple:
        has_image = 1 if e.get("image_kind") == "real" else 0
        has_faq = 1 if e.get("faq") else 0
        body_len = _entry_text_length(e)
        return (has_image + has_faq, body_len, e.get("generated_at", ""))

    ranked = sorted(articles_data, key=score, reverse=True)
    return ranked[:limit]


HERO_TEMPLATE = """<section class="hero">
  <p class="hero-label">TODAY'S TOP STORY</p>
  <a class="hero-link" href="articles/{slug}.html">
    <h2 class="hero-headline">{headline}</h2>
  </a>
  <p class="hero-why">{why}</p>
  <div class="hero-meta"><span>{source}</span><span class="dot">&middot;</span><span>{date}</span>\
<span class="dot">&middot;</span><span>{reading_time}分で読める</span></div>
</section>
"""


def _render_hero(entry: dict) -> str:
    digest = _digest_of(entry)
    why = digest["why"] or digest["what"]
    return HERO_TEMPLATE.format(
        slug=entry["slug"],
        headline=html_lib.escape(entry["headline"]),
        why=html_lib.escape(why),
        source=html_lib.escape(entry["source"]),
        date=entry.get("generated_at", "")[:10],
        reading_time=_reading_time(entry),
    )


TODAY_CARD_TEMPLATE = """<article class="today-card{major_class}">
  <a href="articles/{slug}.html" class="today-card-title">{headline}</a>
  <dl class="today-facts">
    <div class="fact-what"><dt>WHAT HAPPENED</dt><dd>{what}</dd></div>
{why_row}{impact_row}  </dl>
</article>
"""


def _render_todays_briefing(articles_data: list[dict], exclude_slug: str | None = None, limit: int = 5) -> str:
    """「今日、知っておくべきこと」セクション。以前はTODAY IN AI(直近記事を機械的に列挙)と
    TRENDING NOW(実PVが無いので編集部ピックアップ)の2セクションに分かれていたが、
    どちらも実質「重要なものを見せる」という同じ役割だったため統合した。
    importance(major/notable)が付いた記事を優先し、足りない場合のみ情報の厚みベースの
    編集部ピックアップで補う(架空の人気度は作らない、という方針は維持)。"""
    candidates = [e for e in reversed(articles_data) if e["slug"] != exclude_slug]
    important = [e for e in candidates if _entry_importance(e) in ("major", "notable")][:limit]
    if len(important) < min(3, len(candidates)):
        picked_slugs = {e["slug"] for e in important}
        backfill_pool = [e for e in candidates if e["slug"] not in picked_slugs]
        important += _pick_editorial_highlights(backfill_pool, limit - len(important))
    pool = important[:limit]
    if not pool:
        return ""
    cards = []
    for e in pool:
        digest = _digest_of(e)
        why_row = (
            f'    <div class="fact-why"><dt>WHY IT MATTERS</dt><dd>{html_lib.escape(digest["why"])}</dd></div>\n'
            if digest["why"] else ""
        )
        impact_row = (
            f'    <div class="fact-impact"><dt>IMPACT</dt><dd>{html_lib.escape(digest["impact"])}</dd></div>\n'
            if digest["impact"] else ""
        )
        cards.append(
            TODAY_CARD_TEMPLATE.format(
                slug=e["slug"], headline=html_lib.escape(e["headline"]),
                what=html_lib.escape(digest["what"]), why_row=why_row, impact_row=impact_row,
                major_class=" today-card-major" if _entry_importance(e) == "major" else "",
            )
        )
    return (
        '<section class="today-ai" id="today">'
        '<p class="section-label">TODAY\'S BRIEFING</p>'
        '<h2 class="section-title-lg">今日、知っておくべきこと</h2>'
        f'<div class="today-grid">{"".join(cards)}</div>'
        "</section>"
    )


def _render_topics_explore(articles_data: list[dict]) -> str:
    topics = _collect_topics(articles_data)
    if not topics:
        return ""
    tiles = "".join(
        f'<a class="topic-tile" href="topics/{_topic_slug(tag)}.html">#{html_lib.escape(tag)}'
        f'<span class="topic-count">{len(entries)}</span></a>'
        for tag, entries in sorted(topics.items(), key=lambda kv: len(kv[1]), reverse=True)[:12]
    )
    return (
        '<section class="topics-explore" id="topics">'
        '<p class="section-label">TOPICS</p>'
        '<h2 class="section-title-lg">テーマから探す</h2>'
        f'<div class="topics-grid">{tiles}</div>'
        "</section>"
    )


TICKER_ITEM_TEMPLATE = '<a class="mot-ticker-item" href="articles/{slug}.html" style="{bg_style}"><span class="mot-ticker-text">{headline}</span></a>'


def _render_ticker(articles_data: list[dict], exclude_slug: str | None = None, limit: int = 8) -> str:
    """タイトル直下を横に流れる、注目ニュースのティッカー。画像の上に見出しをうっすら重ねて表示する。
    CSSアニメーションでシームレスに無限ループさせるため、同じ並びを2回連結している。"""
    candidates = [e for e in articles_data if e["slug"] != exclude_slug]
    picks = _pick_editorial_highlights(candidates, limit=limit)
    if not picks:
        return ""

    def _item(e: dict) -> str:
        safe_image = _safe_http_url(e.get("image_url")) if e.get("image_kind") == "real" else None
        if safe_image:
            bg_style = f"background-image: url('{html_lib.escape(safe_image)}');"
        else:
            color1, color2 = _pick_gradient(e.get("source", ""))
            bg_style = f"background: linear-gradient(135deg, {color1}, {color2});"
        return TICKER_ITEM_TEMPLATE.format(
            slug=e["slug"], bg_style=bg_style, headline=html_lib.escape(e["headline"])
        )

    items_html = "".join(_item(e) for e in picks)
    return (
        '<div class="mot-ticker" aria-label="注目のニュース">'
        f'<div class="mot-ticker-track">{items_html}{items_html}</div>'
        "</div>"
    )


# サムネイルは画像(実写 or グラデーション背景)の上に見出しを直接重ねて表示する。
# 一覧ページ用(自サイトのarticles/へリンク)と記事ページ用(画像はリンクなし表示)でhrefの扱いが違うため分けている
THUMBNAIL_TEMPLATE = (
    '<a class="thumb-link" href="articles/{slug}.html" style="{bg_style}">{img_tag}'
    '<div class="thumb-overlay"><span class="thumb-overlay-text">{headline}</span></div></a>'
)
ARTICLE_THUMBNAIL_TEMPLATE = (
    '<div class="thumb-link" style="{bg_style}">{img_tag}'
    '<div class="thumb-overlay"><span class="thumb-overlay-text">{headline}</span></div></div>'
)


ABOUT_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{theme_init}
{csp}
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>運営者情報・プライバシーポリシー | AI特化メディアMOT</title>
<meta name="description" content="AI特化メディアMOTの運営者情報・免責事項・著作権・プライバシーポリシーについてのページです。">
<link rel="canonical" href="{page_url}">
<link rel="icon" href="{favicon}">
{google_font}
<link rel="stylesheet" href="style.css">
{goatcounter}
</head>
<body class="article-page">
{nav}
<main>
  <a class="back-link" href="index.html">&laquo; 一覧に戻る</a>
  <h1 class="headline">このサイトについて</h1>

  <h2>サイト概要</h2>
  <p class="summary">当サイトは、生成AI・LLM関連の国内外ニュースをAIが要約し、見出し・記事としてまとめて紹介するニュースキュレーションサイトです。</p>

  <h2>運営者情報</h2>
  <p class="summary">運営者名: AI特化メディアMOT編集部<br>連絡先: <a href="contact.html">お問い合わせページ</a>よりご連絡ください。</p>

  <h2>免責事項</h2>
  <p class="summary">
    当サイトの記事は、各ニュースサイトが公開した情報をもとにAIが要約・作成したものであり、内容の正確性・完全性を保証するものではありません。
    各記事の詳細・一次情報は、記事ページ内の「元記事を読む」リンク先をご確認ください。
    当サイトの情報を利用したことにより生じたいかなる損害についても、運営者は責任を負いかねます。
  </p>

  <h2>著作権について</h2>
  <p class="summary">
    各記事の見出し画像・引用元情報の著作権は、それぞれの発行元に帰属します。当サイトでは元記事の要点を独自の言葉で要約し、
    必ず元記事へのリンクを掲載しています。著作権に関するお問い合わせは上記連絡先までご連絡ください。
  </p>

  <h2>プライバシーポリシー</h2>
  <p class="summary">
    当サイトでは、広告配信のためにCookie等を使用する場合があります。Cookieを使用することで、当サイトはお客様のコンピュータを識別できるようになりますが、
    お客様個人を特定できるものではありません。アクセス解析のためにアクセス解析ツールを使用する場合があります。
  </p>

  <h2>お問い合わせ</h2>
  <p class="summary"><a href="contact.html">お問い合わせページ</a>より受け付けています。</p>
</main>
<footer>
  <a href="index.html">&laquo; トップへ戻る</a>
</footer>
</body>
</html>
"""

CONTACT_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{theme_init}
{csp}
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>お問い合わせ・コラボレーション | AI特化メディアMOT</title>
<meta name="description" content="AI特化メディアMOTへのプロダクト掲載依頼・協業/スポンサー相談・お問い合わせ窓口です。">
<link rel="canonical" href="{page_url}">
<link rel="icon" href="{favicon}">
{google_font}
<link rel="stylesheet" href="style.css">
{goatcounter}
</head>
<body class="article-page">
{nav}
<main>
  <a class="back-link" href="index.html">&laquo; 一覧に戻る</a>
  <h1 class="headline">お問い合わせ・コラボレーション</h1>
  <p class="summary">MOTへのプロダクト掲載依頼、協業・スポンサーのご相談、その他お問い合わせはこちらから受け付けています。内容は編集部が確認のうえ対応します。掲載や採用をお約束するものではありません。</p>

  <div class="contact-card">
    <h2>プロダクトを紹介してほしい</h2>
    <p class="summary">AIツール・アプリ・個人開発のプロダクト・OSS等を作った方は、こちらからMOTに紹介依頼を送れます。内容を確認のうえ、サイトやSNS、MOT Communityで紹介する場合があります。</p>
    <a class="contact-btn" href="https://forms.gle/ifnQPZ6cmDZgFrF77" target="_blank" rel="noopener noreferrer">プロダクトを紹介する &raquo;</a>
  </div>

  <div class="contact-card">
    <h2>協業・スポンサーのご相談</h2>
    <p class="summary">プロダクト紹介、AIサービスの紹介、スポンサー掲載、その他コラボレーションのご相談はこちらから。まずは達成したいことを教えてください。予算感の記載は任意です。</p>
    <a class="contact-btn" href="https://forms.gle/AvexYm3dxnRRRRTf7" target="_blank" rel="noopener noreferrer">相談する &raquo;</a>
  </div>

  <div class="contact-card">
    <h2>一般のお問い合わせ・フィードバック</h2>
    <p class="summary">記事の誤りのご指摘、ご意見・ご感想など、その他のお問い合わせはこちらから。</p>
    <a class="contact-btn" href="https://forms.gle/Dd4UdoYmSarQrFNy6" target="_blank" rel="noopener noreferrer">お問い合わせする &raquo;</a>
  </div>

  <p class="summary" style="margin-top:40px;">MOTはまだ小さなメディアですが、これからもっと多くのAIニュースや情報を届けられる場所にしていきたいと思っています。もしよければ、周りの方にMOTのことを広めてもらえると嬉しいです。</p>

  <p class="summary" style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
    <a href="https://discord.gg/vtBB9s7SS" target="_blank" rel="noopener noreferrer" style="display:inline-flex; align-items:center; gap:6px; color:var(--mot-primary); font-weight:600; text-decoration:none;">
      <svg width="17" height="17" viewBox="0 0 640 512" aria-hidden="true"><path fill="#5865F2" d="M524.531,69.836a1.5,1.5,0,0,0-.764-.7A485.065,485.065,0,0,0,404.081,32.03a1.816,1.816,0,0,0-1.923.91,337.461,337.461,0,0,0-14.9,30.6,447.848,447.848,0,0,0-134.426,0,309.541,309.541,0,0,0-15.135-30.6,1.89,1.89,0,0,0-1.924-.91A483.689,483.689,0,0,0,116.085,69.137a1.712,1.712,0,0,0-.788.676C39.068,183.651,18.186,294.69,28.43,404.354a2.016,2.016,0,0,0,.765,1.375A487.666,487.666,0,0,0,176.02,479.918a1.9,1.9,0,0,0,2.063-.676A348.2,348.2,0,0,0,208.12,430.4a1.86,1.86,0,0,0-1.019-2.588,321.173,321.173,0,0,1-45.868-21.853,1.885,1.885,0,0,1-.185-3.126c3.082-2.309,6.166-4.711,9.109-7.137a1.819,1.819,0,0,1,1.9-.256c96.229,43.917,200.41,43.917,295.5,0a1.812,1.812,0,0,1,1.924.233c2.944,2.426,6.027,4.851,9.132,7.16a1.884,1.884,0,0,1-.162,3.126,301.407,301.407,0,0,1-45.89,21.83,1.875,1.875,0,0,0-1,2.611,391.055,391.055,0,0,0,30.014,48.815,1.864,1.864,0,0,0,2.063.7A486.048,486.048,0,0,0,610.7,405.729a1.882,1.882,0,0,0,.765-1.352C623.729,277.594,590.933,167.465,524.531,69.836ZM222.491,337.58c-28.972,0-52.844-26.587-52.844-59.239S193.056,219.1,222.491,219.1c29.665,0,53.306,26.82,52.843,59.239C275.334,310.993,251.924,337.58,222.491,337.58Zm195.38,0c-28.973,0-52.845-26.587-52.845-59.239S388.437,219.1,417.871,219.1c29.665,0,53.307,26.82,52.844,59.239C470.715,310.993,447.536,337.58,417.871,337.58Z"/></svg>
      MOT Discordコミュニティに参加する
    </a>
    <span style="color:var(--mot-text-secondary); font-size:0.9rem;">みんなでAI開発、ワクワクするものを作りあい高めあう場所です。</span>
  </p>
</main>
<footer>
  <a href="index.html">&laquo; トップへ戻る</a>
</footer>
</body>
</html>
"""

PRODUCTS_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{theme_init}
{csp}
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>プロダクト紹介 | AI特化メディアMOT</title>
<meta name="description" content="AI特化メディアMOTを運営するチームが手がけるサービス・アプリ・プロダクトの紹介ページです。">
<link rel="canonical" href="{page_url}">
<link rel="icon" href="{favicon}">
{google_font}
<link rel="stylesheet" href="style.css">
{goatcounter}
</head>
<body class="article-page">
{nav}
<main>
  <a class="back-link" href="index.html">&laquo; 一覧に戻る</a>
  <h1 class="headline">プロダクト紹介</h1>
  <p class="summary">MOTを運営するチームが手がけている、その他のサービス・アプリ・プロジェクトをこちらでまとめて紹介していきます。</p>
  <p class="summary" style="margin-top:28px;">
    <a href="nagano/index.html" style="font-weight:700;">MOT NAGANO</a><br>
    長野の人と仕事を、ひとつずつ訪ねて記録していくプロジェクトです。まだ始まったばかりです。
  </p>
  <p class="summary">ご自身のプロダクトをMOTで紹介してほしい方は<a href="contact.html">お問い合わせページ</a>からどうぞ。</p>
</main>
<footer>
  <a href="index.html">&laquo; トップへ戻る</a>
</footer>
</body>
</html>
"""


def _load_articles_data() -> list[dict]:
    if not ARTICLES_DATA_PATH.exists():
        return []
    try:
        return json.loads(ARTICLES_DATA_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_articles_data(entries: list[dict]) -> None:
    ARTICLES_DATA_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


_ENTITY_TOKEN_RE = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ0-9０-９]+|[ァ-ヴー]{2,}")


def _extract_keywords(entry: dict) -> set[str]:
    """記事の見出し・出典・タグから、企業名/製品名らしきトークン(英数字・カタカナ連続)を抽出する。
    関連記事の選定(同じサービス・企業・技術のテーマでリンクする)に使う簡易的なキーワード抽出。"""
    tags = {t.strip() for t in (entry.get("tags") or []) if t.strip()}
    text = f"{entry.get('headline', '')} {entry.get('source', '')}"
    tokens = {t for t in _ENTITY_TOKEN_RE.findall(text) if len(t) >= 2}
    return tags | tokens


def _related_entries(entry: dict, articles_data: list[dict], limit: int) -> list[dict]:
    """同じテーマ・企業・サービスのキーワードが重なる記事を優先し、重なりが無ければ新しい順で選ぶ。"""
    keywords = _extract_keywords(entry)
    candidates = [e for e in articles_data if e["slug"] != entry["slug"]]

    def score(other: dict) -> tuple[int, str]:
        overlap = len(keywords & _extract_keywords(other))
        return (overlap, other.get("generated_at", ""))

    candidates.sort(key=score, reverse=True)
    return candidates[:limit]


def _topic_slug(tag: str) -> str:
    """タグをURL用スラッグに変換する。完全に英数字のタグはそのまま、
    それ以外(日本語を含む等)はハッシュ化する。
    注意: 元のタグが完全ASCIIかどうかを先に判定すること。
    (「教育AI」から先に非ASCII文字だけ除去すると"ai"になり、単独タグ"AI"と衝突するバグを防ぐ)"""
    normalized = tag.strip().lower()
    if normalized and all(ord(c) < 128 for c in normalized):
        ascii_slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
        if ascii_slug:
            return ascii_slug
    return hashlib.sha1(tag.encode("utf-8")).hexdigest()[:10]


def _collect_topics(articles_data: list[dict]) -> dict[str, list[dict]]:
    """タグ名(表示用の元の文字列) -> そのタグを持つ記事一覧(新しい順)。
    MIN_TOPIC_ARTICLES件未満のテーマはページを作らない(内容の薄いページを量産しないため)。"""
    by_tag: dict[str, list[dict]] = {}
    for entry in reversed(articles_data):  # 新しい順
        for tag in entry.get("tags") or []:
            tag = tag.strip()
            if not tag:
                continue
            by_tag.setdefault(tag, []).append(entry)
    return {tag: entries for tag, entries in by_tag.items() if len(entries) >= MIN_TOPIC_ARTICLES}


TAG_PILL_TEMPLATE = '<a class="tag-pill" href="{href}">#{tag}</a>'


def _render_tag_pills(entry: dict, prefix: str = "", valid_topic_tags: set[str] | None = None) -> str:
    """記事ページに表示するタグのピル。トピックページ(prefix="../topics/")と
    記事ページ(prefix="topics/")のどちらからでも呼べるよう相対パスを引数化。
    valid_topic_tagsが指定された場合、実際にハブページが存在するタグのみ表示する(リンク切れ防止)。"""
    tags = [t.strip() for t in (entry.get("tags") or []) if t.strip()]
    if valid_topic_tags is not None:
        tags = [t for t in tags if t in valid_topic_tags]
    if not tags:
        return ""
    pills = "".join(
        TAG_PILL_TEMPLATE.format(href=f"{prefix}{_topic_slug(t)}.html", tag=html_lib.escape(t)) for t in tags
    )
    return f'<div class="tag-pills">{pills}</div>'


def _render_tag_tracker(entry: dict) -> str:
    """CONTINUE EXPLORING用に、閲覧したタグをこの端末のlocalStorageにだけ記録する
    (サーバーには一切送信しない)。実際の記録・判定ロジックはshare.js側にまとめてある。"""
    tags = [t.strip() for t in (entry.get("tags") or []) if t.strip()]
    if not tags:
        return ""
    tags_json = json.dumps(tags, ensure_ascii=False).replace("</", "<\\/")
    return f"<script>window.motPageTags={tags_json};</script>"



TOPIC_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{theme_init}
{csp}
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{tag}の最新ニュースまとめ | AI特化メディアMOT</title>
<meta name="description" content="{tag}に関するAI最新ニュースをまとめて紹介。関連記事{count}件を新着順に掲載しています。">
<link rel="canonical" href="{page_url}">
<link rel="icon" href="{favicon}">
{google_font}
<link rel="stylesheet" href="../style.css">
{goatcounter}
<meta property="og:type" content="website">
<meta property="og:site_name" content="AI特化メディアMOT">
<meta property="og:title" content="{tag}の最新ニュースまとめ | AI特化メディアMOT">
<meta property="og:description" content="{tag}に関するAI最新ニュースをまとめて紹介。">
<meta property="og:image" content="{site_logo}">
<meta property="og:url" content="{page_url}">
<meta name="twitter:card" content="summary">
<meta name="twitter:image" content="{site_logo}">
{structured_data}
</head>
<body>
{nav}
<main class="mot-main">
<a class="back-link" href="../index.html">&laquo; 一覧に戻る</a>
<h2 class="section-title-lg">#{tag} の最新ニュース({count}件)</h2>
{cards}
</main>
<footer>
  <a href="index.html">&laquo; テーマ一覧へ</a>　|　<a href="../index.html">トップへ戻る</a>
</footer>
</body>
</html>
"""

TOPICS_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
{theme_init}
{csp}
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>テーマ別まとめ一覧 | AI特化メディアMOT</title>
<meta name="description" content="ChatGPT・Claude・Gemini等、企業・サービス別にAIニュースをまとめて読めるテーマ一覧ページです。">
<link rel="canonical" href="{page_url}">
<link rel="icon" href="{favicon}">
{google_font}
<link rel="stylesheet" href="../style.css">
{goatcounter}
</head>
<body>
{nav}
<main>
<a class="back-link" href="../index.html">&laquo; 一覧に戻る</a>
<h2 class="section-heading">テーマ別まとめ</h2>
<div class="tag-pills tag-pills-large">
{pills}
</div>
</main>
<footer>
  <a href="../index.html">&laquo; トップへ戻る</a>
</footer>
</body>
</html>
"""


def _write_topic_pages(articles_data: list[dict]) -> list[str]:
    """タグごとのテーマ別ハブページとテーマ一覧ページを書き出す。戻り値はsitemap登録用のURL一覧。"""
    topics = _collect_topics(articles_data)
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)

    urls = []
    for tag, entries in topics.items():
        slug = _topic_slug(tag)
        cards_html = []
        for entry in entries[:MAX_INDEX_ARTICLES]:
            thumbnail = _render_thumbnail(
                entry["image_url"], entry["image_kind"], entry["source"], entry["slug"], entry["headline"],
                for_article_page=False, tags=entry.get("tags"),
            )
            # index.html基準の相対パス(articles/xxx.html)で組み立ててから、
            # topics/配下のページ用にまとめて一段深いパス(../articles/xxx.html)へ補正する
            card_html = CARD_TEMPLATE.format(
                new_badge=NEW_BADGE_HTML if _is_new(entry["generated_at"]) else "",
                thumbnail=thumbnail,
                thumb_share=_thumb_share_html(entry["slug"], entry["headline"]),
                slug=entry["slug"],
                headline=html_lib.escape(entry["headline"]),
                source=html_lib.escape(entry["source"]),
                summary=html_lib.escape(entry["summary"]),
                reading_time=_reading_time(entry),
                search_text=html_lib.escape(entry["headline"]),
                level=_entry_level(entry),
                level_badge=_level_badge(entry),
                card_tags=_render_card_tags(entry),
                ad_code="",
                importance_class=" card-minor" if _entry_importance(entry) == "minor" else "",
            )
            cards_html.append(card_html.replace('href="articles/', 'href="../articles/'))
        page_url = _abs_url(f"topics/{slug}.html")
        breadcrumb_items = [
            ("ホーム", _abs_url("index.html")),
            ("テーマ一覧", _abs_url("topics/index.html")),
            (tag, page_url),
        ]
        (TOPICS_DIR / f"{slug}.html").write_text(
            TOPIC_PAGE_TEMPLATE.format(
                tag=html_lib.escape(tag),
                count=len(entries),
                cards="".join(cards_html),
                favicon=FAVICON_DATA_URI,
                page_url=page_url,
                structured_data=_render_breadcrumb_jsonld(breadcrumb_items),
                site_logo=_abs_url("og-image.png"),
                goatcounter=GOATCOUNTER_SCRIPT,
                csp=CSP_META,
                google_font=GOOGLE_FONT_LINK,
                theme_init=THEME_INIT_SCRIPT,
                nav=_render_sub_nav("../", page_url),
            ),
            encoding="utf-8",
        )
        urls.append(page_url)

    pills = "".join(
        f'<a class="tag-pill" href="{_topic_slug(tag)}.html">#{html_lib.escape(tag)}({len(entries)})</a>'
        for tag, entries in sorted(topics.items(), key=lambda kv: len(kv[1]), reverse=True)
    ) or "<p>まだテーマページがありません。</p>"

    topics_index_url = _abs_url("topics/index.html")
    (TOPICS_DIR / "index.html").write_text(
        TOPICS_INDEX_TEMPLATE.format(
            pills=pills, favicon=FAVICON_DATA_URI, page_url=topics_index_url,
            goatcounter=GOATCOUNTER_SCRIPT, csp=CSP_META, google_font=GOOGLE_FONT_LINK,
            theme_init=THEME_INIT_SCRIPT, nav=_render_sub_nav("../", topics_index_url),
        ),
        encoding="utf-8",
    )
    urls.append(topics_index_url)
    return urls


def _iso_datetime(generated_at: str) -> str:
    try:
        dt = datetime.strptime(generated_at, "%Y-%m-%d %H:%M")
    except ValueError:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:00+09:00")


FAQ_TEMPLATE = """<div class="article-faq">
  <h2>よくある質問</h2>
{items}
</div>"""
FAQ_ITEM_TEMPLATE = """  <div class="faq-item">
    <p class="faq-q">Q. {q}</p>
    <p class="faq-a">{a}</p>
  </div>"""


def _render_faq_html(faq: list[dict] | None) -> str:
    """検索意図(とは/料金/使い方等)に答えるQ&Aを記事ページに表示用HTMLとして描画する。
    JSON-LDのFAQPageと内容を一致させる(構造化データのみに存在する情報を作らないため)。"""
    items = [f for f in (faq or []) if f.get("q") and f.get("a")]
    if not items:
        return ""
    items_html = "\n".join(
        FAQ_ITEM_TEMPLATE.format(q=html_lib.escape(f["q"]), a=html_lib.escape(f["a"])) for f in items
    )
    return FAQ_TEMPLATE.format(items=items_html)


def _mot_organization() -> dict:
    """NewsArticleのauthor/publisherや、サイト全体のOrganization/WebSite JSON-LDで共通して使う
    運営organization情報。sameAsで公式Xアカウントと紐付け、実在媒体であることをAIに伝える。"""
    org = {"@type": "Organization", "name": "AI特化メディアMOT"}
    if SITE_SOCIAL_LINKS:
        org["sameAs"] = SITE_SOCIAL_LINKS
    return org


def _render_organization_jsonld() -> str:
    """トップページに埋め込むWebSite+Organizationの構造化データ。"""
    data = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "AI特化メディアMOT",
        "url": _abs_url("index.html"),
        "publisher": _mot_organization(),
    }
    safe = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">{safe}</script>'


def _render_structured_data(entry: dict, page_url: str, og_image: str) -> str:
    """NewsArticle(+ FAQがあればFAQPage)のJSON-LD構造化データを生成する。
    可視のFAQ表示(_render_faq_html)と同じデータのみを使い、非表示情報を作らない。"""
    published = _iso_datetime(entry["generated_at"])
    data: dict = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": entry["headline"],
        "description": entry["summary"],
        "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
        "author": _mot_organization(),
        "publisher": _mot_organization(),
    }
    if published:
        data["datePublished"] = published
        data["dateModified"] = published
    if og_image:
        data["image"] = [og_image]
    safe_source_url = _safe_http_url(entry.get("link"))
    if safe_source_url:
        data["citation"] = safe_source_url

    scripts = [json.dumps(data, ensure_ascii=False)]

    faq_items = [f for f in (entry.get("faq") or []) if f.get("q") and f.get("a")]
    if faq_items:
        faq_data = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": f["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": f["a"]},
                }
                for f in faq_items
            ],
        }
        scripts.append(json.dumps(faq_data, ensure_ascii=False))

    # </script>によるタグ混入対策(JSON文字列側だけをエスケープする。scriptタグ自体は壊さない)
    safe_scripts = [s.replace("</", "<\\/") for s in scripts]
    return "\n".join(f'<script type="application/ld+json">{s}</script>' for s in safe_scripts)


def _render_breadcrumb_jsonld(items: list[tuple[str, str]]) -> str:
    """パンくずリスト(BreadcrumbList)のJSON-LDを生成する。items: [(表示名, URL), ...] を先頭から順に。
    サイト階層をAIクローラーに伝え、検索結果でのパンくず表示にもつながる。"""
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
            for i, (name, url) in enumerate(items)
        ],
    }
    safe = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">{safe}</script>'


def _render_body_paragraphs(body_text: str) -> str:
    """本文を"\n\n"区切りの段落として<p>タグに分割する。改行が無い旧データはそのまま1段落として扱う。"""
    paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [body_text]
    return "".join(f"<p>{html_lib.escape(p)}</p>" for p in paragraphs)


def _render_article_body(entry: dict) -> str:
    """記事本文のHTML化。新形式(TL;DR+6セクション)があればそれを使い、無ければ
    旧形式(TL;DR+3見出し)、それも無い最古の記事は段落分割のみで表示する
    (テンプレート変更は常に新規記事のみに適用し、過去記事は非破壊)。"""
    if entry.get("content_format") == "foreign_discovery":
        return (
            f'<p class="tldr"><strong>TL;DR</strong> {html_lib.escape(entry["tldr"])}</p>'
            f"<h3>何が起きたか</h3><p>{html_lib.escape(entry['what_happened'])}</p>"
            f'<div class="overseas-box"><h3>海外ではどう報道されているか</h3>'
            f"<p>{html_lib.escape(entry['overseas_report'])}</p></div>"
            f"<h3>なぜ重要か</h3><p>{html_lib.escape(entry['why_it_matters'])}</p>"
            f'<div class="japan-impact-box"><h3>日本への影響</h3>'
            f"<p>{html_lib.escape(entry['japan_impact'])}</p></div>"
            f"<h3>今後どうなる</h3><p>{html_lib.escape(entry['outlook'])}</p>"
        ) + (
            f'<div class="mot-take-box"><h3>MOTの見解</h3><p>{html_lib.escape(entry["mot_take"])}</p></div>'
            if entry.get("mot_take") and entry["mot_take"].strip() else ""
        ) + (
            f'<div class="watch-next-box"><h3>今後の注目ポイント</h3>'
            f'<p>{html_lib.escape(entry["what_to_watch_next"])}</p></div>'
            if entry.get("what_to_watch_next") and entry["what_to_watch_next"].strip() else ""
        )

    tldr = entry.get("tldr")
    what = entry.get("what_happened")
    why = entry.get("why_it_matters")
    impact_on_reader = entry.get("impact_on_reader")
    relevance = entry.get("reader_relevance")
    risk = entry.get("risk_point")
    opportunity = entry.get("opportunity_point")

    mot_take = entry.get("mot_take")
    watch_next = entry.get("what_to_watch_next")
    if tldr and what and why and impact_on_reader and relevance and risk and opportunity:
        mot_take_html = ""
        if mot_take and mot_take.strip():
            mot_take_html = (
                f'<div class="mot-take-box"><h3>MOTの見解</h3>'
                f"<p>{html_lib.escape(mot_take)}</p></div>"
            )
        watch_next_html = ""
        if watch_next and watch_next.strip():
            watch_next_html = (
                f'<div class="watch-next-box"><h3>今後の注目ポイント</h3>'
                f"<p>{html_lib.escape(watch_next)}</p></div>"
            )
        return (
            f'<p class="tldr"><strong>TL;DR</strong> {html_lib.escape(tldr)}</p>'
            f"<h3>何が起きたか</h3><p>{html_lib.escape(what)}</p>"
            f"<h3>なぜ重要か</h3><p>{html_lib.escape(why)}</p>"
            f"<h3>あなたへの影響</h3><p>{html_lib.escape(impact_on_reader)}</p>"
            f"<h3>MOT読者が知っておくべき理由</h3><p>{html_lib.escape(relevance)}</p>"
            f'<div class="risk-box"><h3>知らないと生まれる差</h3><p>{html_lib.escape(risk)}</p></div>'
            f'<div class="opportunity-box"><h3>これを知ることで得られるチャンス</h3>'
            f"<p>{html_lib.escape(opportunity)}</p></div>"
            f"{mot_take_html}"
            f"{watch_next_html}"
        )

    legacy_impact = entry.get("future_impact")
    if tldr and what and why and legacy_impact:
        return (
            f'<p class="tldr"><strong>TL;DR</strong> {html_lib.escape(tldr)}</p>'
            f"<h3>何が起きたか</h3><p>{html_lib.escape(what)}</p>"
            f"<h3>なぜ重要か</h3><p>{html_lib.escape(why)}</p>"
            f"<h3>今後の影響</h3><p>{html_lib.escape(legacy_impact)}</p>"
        )
    return _render_body_paragraphs(entry.get("body") or entry.get("summary") or "")


def _entry_text_length(entry: dict) -> int:
    """本文の分量(文字数)。新形式(TL;DR+6セクション)/旧形式(TL;DR+3見出し)/最古の形式(body)
    いずれのデータにも対応する。読了時間の概算や、PVデータ不在時の編集部ピックアップの
    厚み判定に使う。"""
    body = entry.get("body")
    if body:
        return len(body)
    parts = (
        entry.get("tldr"), entry.get("what_happened"), entry.get("why_it_matters"),
        entry.get("impact_on_reader"), entry.get("reader_relevance"),
        entry.get("risk_point"), entry.get("opportunity_point"),
        entry.get("future_impact"),
    )
    return sum(len(p) for p in parts if p)


def _make_slug(link: str, tags: list[str] | None = None) -> str:
    """URLスラッグを生成する。タグ(企業名・製品名等)がASCIIで取れれば意味のある接頭辞にし、
    一意性はハッシュ値で担保する(タグが同じ記事が複数あっても衝突しない)。
    タグが無い/日本語のみの場合はハッシュのみ(従来と同じ)。"""
    link_hash = hashlib.sha1(link.encode("utf-8")).hexdigest()[:8]
    keywords = []
    for tag in tags or []:
        ascii_part = re.sub(r"[^a-z0-9]+", "-", tag.strip().lower()).strip("-")
        if ascii_part:
            keywords.append(ascii_part)
        if len(keywords) >= 2:
            break
    if keywords:
        return f"{'-'.join(keywords)}-{link_hash}"
    return link_hash


def _is_new(generated_at: str) -> bool:
    try:
        generated = datetime.strptime(generated_at, "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return (datetime.now() - generated).total_seconds() < NEW_BADGE_HOURS * 3600


# 難易度判定: 一次情報・技術者向けソースのドメインを「テクニカル」とし、それ以外は「やさしい」とする。
# 記事ごとにLLMで判定するとコスト・ブレが出るため、出典ドメインという機械的な基準で決める。
TECHNICAL_DOMAINS = {
    "arxiv.org", "huggingface.co", "openai.com", "deepmind.google",
    "qiita.com", "zenn.dev", "marktechpost.com", "the-decoder.com",
    "arstechnica.com", "simonwillison.net",
}
LEVEL_LABELS = {"technical": "テクニカル", "easy": "やさしい"}


def _classify_level(source_domain: str | None) -> str:
    domain = (source_domain or "").lower().removeprefix("www.")
    return "technical" if domain in TECHNICAL_DOMAINS else "easy"


def _entry_level(entry: dict) -> str:
    """levelフィールドが無い旧記事は「やさしい」扱いにする(多くが一般ニュース由来のため)。"""
    level = entry.get("level")
    return level if level in LEVEL_LABELS else "easy"


_VALID_IMPORTANCE = {"major", "notable", "minor"}


def _entry_importance(entry: dict) -> str:
    """記事の重要度を3段階(major/notable/minor)で返す。
    新形式のimportance_score(0〜100の整数)があればそこから判定し、
    それが無い旧記事は当時のimportance分類(major/notable/minor)、
    どちらも無いさらに古い記事はnotable扱いにする(安全側のフォールバック)。"""
    score = entry.get("importance_score")
    if isinstance(score, (int, float)):
        if score >= 75:
            return "major"
        if score >= 40:
            return "notable"
        return "minor"
    legacy = entry.get("importance")
    return legacy if legacy in _VALID_IMPORTANCE else "notable"


def _level_badge(entry: dict) -> str:
    level = _entry_level(entry)
    icon = "&#128309;" if level == "technical" else "&#128994;"
    return f'<span class="level-badge level-{level}">{icon} {LEVEL_LABELS[level]}</span>'


def _render_card_tags(entry: dict, limit: int = 3) -> str:
    """一覧カードに表示する小さめのタグ。クリック前に「何についての記事か」を伝える
    (Information Scent向上)。リンク切れ防止のためテーマページが実在するタグのみ表示する想定は
    ここでは省略し(一覧は頻繁に再生成されるため実質問題にならない)、タグ名の表示のみ行う。"""
    tags = [t.strip() for t in (entry.get("tags") or []) if t.strip()][:limit]
    if not tags:
        return ""
    chips = "".join(f'<span class="tag-pill tag-pill-sm">#{html_lib.escape(t)}</span>' for t in tags)
    return f'<div class="tag-pills card-tags">{chips}</div>'


CHARS_PER_MINUTE = 500  # 日本語の平均的な黙読速度の目安


def _reading_time(entry: dict) -> int:
    """本文の文字数から読了時間(分)を概算する。LLM不要、最低1分。"""
    body_len = _entry_text_length(entry) or len(entry.get("summary") or "")
    return max(1, round(body_len / CHARS_PER_MINUTE))


def _digest_of(entry: dict) -> dict:
    """digestフィールドが無い旧記事にも対応する安全な取得(summaryにフォールバック)。"""
    digest = entry.get("digest") or {}
    return {
        "what": digest.get("what") or entry.get("summary", ""),
        "why": digest.get("why") or "",
        "impact": digest.get("impact") or "",
    }


def _load_alert_state() -> dict:
    if not ALERT_STATE_PATH.exists():
        return {"consecutive_empty_runs": 0, "alerted": False}
    try:
        return json.loads(ALERT_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"consecutive_empty_runs": 0, "alerted": False}


def _save_alert_state(state_data: dict) -> None:
    ALERT_STATE_PATH.write_text(json.dumps(state_data, ensure_ascii=False), encoding="utf-8")


def _record_run_result(got_new_articles: bool) -> None:
    """新規記事が連続で取得できていない場合、Gmailでアラートを送る(ニュース取得停止に気づくため)。"""
    st = _load_alert_state()
    if got_new_articles:
        if st["consecutive_empty_runs"] > 0 or st["alerted"]:
            _save_alert_state({"consecutive_empty_runs": 0, "alerted": False})
        return

    st["consecutive_empty_runs"] += 1
    if st["consecutive_empty_runs"] >= STALE_ALERT_THRESHOLD and not st["alerted"]:
        sent = alert.send_alert(
            "MOTのニュース自動取得が止まっている可能性",
            f"直近{st['consecutive_empty_runs']}回の実行で新規記事が0件でした。"
            "RSSフィードの変更やAPI障害の可能性があります。logs/ai_news_run.logを確認してください。",
        )
        st["alerted"] = sent
    _save_alert_state(st)


def _maybe_send_daily_digest() -> None:
    """朝の実行時に1日1回だけ、直近24時間の集計結果をメールで送る。"""
    now = datetime.now()
    if not (DIGEST_HOUR_RANGE[0] <= now.hour <= DIGEST_HOUR_RANGE[1]):
        return

    today_str = now.strftime("%Y-%m-%d")
    digest_state = {}
    if DIGEST_STATE_PATH.exists():
        try:
            digest_state = json.loads(DIGEST_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            digest_state = {}
    if digest_state.get("last_sent_date") == today_str:
        return

    articles_data = _load_articles_data()
    cutoff = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    recent = [a for a in articles_data if a.get("generated_at", "") >= cutoff]
    source_counts = Counter(a.get("source", "?") for a in recent)

    lines = [
        f"MOT 日次レポート ({today_str})",
        "",
        f"直近24時間の新規記事: {len(recent)}件",
        f"サイト全体の総記事数: {len(articles_data)}件",
        "",
    ]
    if recent:
        lines.append("--- 直近24時間の新着記事 ---")
        for a in recent:
            lines.append(f"・{a.get('headline', '?')}（{a.get('source', '?')}）")
        lines.append("")
        lines.append("--- ソース別内訳(直近24時間) ---")
        for src, cnt in source_counts.most_common(10):
            lines.append(f"{cnt:3d}件  {src}")
    else:
        lines.append("直近24時間で新規記事はありませんでした。")

    gc_stats = goatcounter.fetch_recent_stats(days=1)
    lines.append("")
    if gc_stats is not None:
        lines.append(f"--- アクセス数(直近24時間、GoatCounter実データ) ---")
        lines.append(f"合計PV: {gc_stats['total_pv']}")
        for page in gc_stats["top_pages"][:5]:
            lines.append(f"{page['count']:3d}PV  {page['path']}")
    else:
        lines.append("(アクセス数: GoatCounterからの取得に失敗、または未設定)")

    lines.append("")
    lines.append(f"サイト: {SITE_BASE_URL}/")

    sent = alert.send_digest(f"{today_str}の集計結果", "\n".join(lines))
    if sent:
        DIGEST_STATE_PATH.write_text(
            json.dumps({"last_sent_date": today_str}, ensure_ascii=False), encoding="utf-8"
        )


FABLE_ATLAS_DEDUP_PATH = Path(__file__).parent / "fable_atlas_seen.json"
FABLE_ATLAS_DEDUP_WINDOW_HOURS = 20  # 同じ話題(例: 「Fable 5.1」)はこの時間内は重複記事化しない
_FABLE_ATLAS_SIG_RE = re.compile(
    r"(Claude\s*Fable\s*\d+(?:\.\d+)*|Claude\s*Mythos\s*\d+(?:\.\d+)*|ChatGPT\s*Atlas|OpenAI\s*Atlas)",
    re.IGNORECASE,
)


def _fable_atlas_signatures(text: str) -> set[str]:
    return {re.sub(r"\s+", "", m.group(0)).lower() for m in _FABLE_ATLAS_SIG_RE.finditer(text or "")}


def _load_fable_atlas_seen() -> dict:
    if not FABLE_ATLAS_DEDUP_PATH.exists():
        return {}
    try:
        return json.loads(FABLE_ATLAS_DEDUP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fable_atlas_is_duplicate(article) -> bool:
    """複数メディアが同じ発表を報じるため、同じ製品バージョンの話題は
    一定時間内は2記事目を作らない(記事の量産的な重複を防ぐ)。"""
    sigs = _fable_atlas_signatures(f"{article.title} {article.summary}")
    if not sigs:
        return False
    seen = _load_fable_atlas_seen()
    now = datetime.now()
    for sig in sigs:
        ts = seen.get(sig)
        if ts:
            try:
                if now - datetime.fromisoformat(ts) < timedelta(hours=FABLE_ATLAS_DEDUP_WINDOW_HOURS):
                    return True
            except ValueError:
                continue
    return False


def _fable_atlas_record(article) -> None:
    sigs = _fable_atlas_signatures(f"{article.title} {article.summary}")
    if not sigs:
        return
    seen = _load_fable_atlas_seen()
    now_iso = datetime.now().isoformat(timespec="seconds")
    for sig in sigs:
        seen[sig] = now_iso
    cutoff = datetime.now() - timedelta(hours=FABLE_ATLAS_DEDUP_WINDOW_HOURS * 3)
    seen = {
        k: v for k, v in seen.items()
        if _safe_parse_iso(v) is None or _safe_parse_iso(v) > cutoff
    }
    FABLE_ATLAS_DEDUP_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


_STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "on", "for", "is", "are", "was", "were",
    "with", "at", "by", "from", "as", "it", "its", "new", "now", "how", "why",
    "and", "or", "but", "after", "over", "into", "about", "your", "you", "what",
    "this", "that", "will", "has", "have", "says", "say", "said", "amid",
}


def _significant_tokens(title: str) -> set[str]:
    """英語タイトルから、固有名詞・製品名らしき語だけを残す軽量トークナイザ
    (ストップワードと短い語を除く)。AI呼び出し無しの重複検出に使う。"""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'.-]*", title.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _group_candidates_by_topic(articles: list) -> list[list]:
    """同一の出来事を報じた複数媒体の記事をまとめる(タイトルの有意語の重なりベース)。
    埋め込みAI等は使わず、コストゼロの簡易クラスタリング。"""
    groups: list[list] = []
    sigs: list[set[str]] = []
    for art in articles:
        tokens = _significant_tokens(art.title)
        if not tokens:
            groups.append([art])
            sigs.append(tokens)
            continue
        matched_index = None
        for i, sig in enumerate(sigs):
            if not sig:
                continue
            overlap = len(tokens & sig) / max(1, min(len(tokens), len(sig)))
            if overlap >= 0.5:
                matched_index = i
                break
        if matched_index is None:
            groups.append([art])
            sigs.append(tokens)
        else:
            groups[matched_index].append(art)
            sigs[matched_index] |= tokens
    return groups


FOREIGN_DISCOVERY_DEDUP_PATH = Path(__file__).parent / "foreign_discovery_seen.json"
FOREIGN_DISCOVERY_DEDUP_WINDOW_HOURS = 96  # 別の記事URLで同じ出来事が再度報じられても4日は重複記事化しない


def _load_foreign_discovery_seen() -> list[dict]:
    if not FOREIGN_DISCOVERY_DEDUP_PATH.exists():
        return []
    try:
        return json.loads(FOREIGN_DISCOVERY_DEDUP_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _foreign_discovery_is_duplicate(article) -> bool:
    """FableAtlasウォッチと違い出来事の種類が定まらないため、正規表現ではなく
    タイトルの有意語の重なり(Jaccard)で判定する。実行をまたいでも(別URL・別媒体
    での再報道でも)同じ出来事の記事を量産しないためのガード。"""
    tokens = _significant_tokens(article.title)
    if not tokens:
        return False
    seen = _load_foreign_discovery_seen()
    cutoff = datetime.now() - timedelta(hours=FOREIGN_DISCOVERY_DEDUP_WINDOW_HOURS)
    for item in seen:
        ts = _safe_parse_iso(item.get("ts", ""))
        if ts is None or ts < cutoff:
            continue
        prev_tokens = set(item.get("tokens") or [])
        if not prev_tokens:
            continue
        overlap = len(tokens & prev_tokens) / max(1, min(len(tokens), len(prev_tokens)))
        if overlap >= 0.5:
            return True
    return False


def _foreign_discovery_record(article) -> None:
    tokens = _significant_tokens(article.title)
    if not tokens:
        return
    seen = _load_foreign_discovery_seen()
    seen.append({"tokens": sorted(tokens), "ts": datetime.now().isoformat(timespec="seconds")})
    cutoff = datetime.now() - timedelta(hours=FOREIGN_DISCOVERY_DEDUP_WINDOW_HOURS * 2)
    seen = [s for s in seen if (_safe_parse_iso(s.get("ts", "")) or datetime.now()) > cutoff]
    FOREIGN_DISCOVERY_DEDUP_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")


def build_foreign_discovery(max_new: int = 2) -> None:
    """海外Tier1/2メディア(BBC/CNBC/The Verge/WIRED/MIT Technology Review)から
    AI関連ニュースを探し、確認なしで自動公開する(編集を経た報道機関のみが対象。
    Tier3の個人発信は別途build_trend_candidates()で候補一覧化するのみに留める)。"""
    posted_links = state.get_posted_links()
    articles = sources.fetch_candidates(feeds=list(sources.FOREIGN_TIER_FEEDS.keys()))
    articles = [a for a in articles if sources.is_ai_relevant(a)]
    candidates = sources.filter_unposted(articles, posted_links)
    if not candidates:
        logger.info("海外発見ニュース: 新規候補がありませんでした。")
        return

    groups = _group_candidates_by_topic(candidates)
    # 複数媒体が報じているグループ(裏付けが強い)を優先
    groups.sort(key=len, reverse=True)

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    articles_data = _load_articles_data()
    new_entries: list[dict] = []

    for group in groups:
        if len(new_entries) >= max_new:
            break
        primary = group[0]
        safe_link = _safe_http_url(primary.link)
        if not safe_link:
            for a in group:
                state.record_posted(a.link)
            continue

        if _foreign_discovery_is_duplicate(primary):
            logger.info("海外発見ニュース: 既報の話題のためスキップ: %s", primary.title)
            for a in group:
                state.record_posted(a.link)
            continue

        meta = sources.get_foreign_source_meta(primary.source_domain)
        if meta is None:
            logger.warning(
                "海外発見ニュース: ドメイン未登録のためデフォルト信頼度を使用: %s (%s)",
                primary.source_domain, primary.link,
            )
            meta = {"name": primary.source, "country": "US", "tier": 2, "reliability_score": 70, "speed_score": 70}
        source_name = meta.get("name") or primary.source

        try:
            result = generator.generate_foreign_discovery_article(group)
        except Exception:
            logger.exception("海外発見記事の生成に失敗したためスキップ: %s", primary.link)
            continue

        slug = _make_slug(safe_link, result.get("tags"))
        image_url = _safe_http_url(sources.fetch_og_image(primary.link))
        image_kind = "real" if image_url else "fallback"

        entry = {
            "slug": slug,
            "link": safe_link,
            "headline": result["headline"],
            "seo_title": result.get("seo_title") or result["headline"],
            "summary": result["summary"],
            "importance_score": result["importance_score"],
            "buzz_score": result["buzz_score"],
            "recommend_score": result["recommend_score"],
            "content_format": "foreign_discovery",
            "tldr": result["tldr"],
            "what_happened": result["what_happened"],
            "overseas_report": result["overseas_report"],
            "why_it_matters": result["why_it_matters"],
            "japan_impact": result["japan_impact"],
            "outlook": result["outlook"],
            "mot_take": result.get("mot_take") or "",
            "what_to_watch_next": result.get("what_to_watch_next") or "",
            "tags": result.get("tags") or [],
            "faq": result.get("faq") or [],
            "digest": result.get("digest") or {},
            "source": source_name,
            "image_url": image_url,
            "image_kind": image_kind,
            "level": _classify_level(primary.source_domain),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source_country": meta.get("country"),
            "source_tier": meta.get("tier"),
            "reliability_score": meta.get("reliability_score"),
            "speed_score": meta.get("speed_score"),
            "novelty_score": result["novelty_score"],
            "japan_relevance_score": result["japan_relevance_score"],
            "growth_potential_score": result["growth_potential_score"],
            "seo_potential_score": result["seo_potential_score"],
            "social_impact_score": result["social_impact_score"],
            "verification_status": "multiple_sources" if len(group) > 1 else "single_source",
            "corroborating_sources": [a.source for a in group[1:3]],
        }
        articles_data.append(entry)
        new_entries.append(entry)
        for a in group:
            state.record_posted(a.link)
        _foreign_discovery_record(primary)
        logger.info(
            "海外発見記事生成成功(裏付け%d件): %s -> articles/%s.html",
            len(group), primary.link, slug,
        )

    if not new_entries:
        logger.info("海外発見ニュース: 生成できた記事がありませんでした。")
        return

    valid_topic_tags = set(_collect_topics(articles_data))
    for entry in new_entries:
        _write_article_page(entry, articles_data, valid_topic_tags)

    if len(articles_data) > MAX_STORED_ARTICLES:
        overflow = articles_data[: len(articles_data) - MAX_STORED_ARTICLES]
        articles_data = articles_data[len(articles_data) - MAX_STORED_ARTICLES :]
        for old in overflow:
            old_path = ARTICLES_DIR / f"{old['slug']}.html"
            old_path.unlink(missing_ok=True)

    _save_articles_data(articles_data)
    _write_index_and_meta(articles_data, len(new_entries))


def build(feeds: list[str] | None = None, max_new: int | None = None) -> None:
    """feeds/max_newを指定すると、特定トピックだけを狙う専用実行になる
    (例: Fable/Atlasウォッチ)。指定しなければ通常の全ソース巡回。"""
    max_new = max_new if max_new is not None else MAX_NEW_ARTICLES
    if feeds is None:
        _maybe_send_daily_digest()
    posted_links = state.get_posted_links()
    articles = sources.fetch_candidates(feeds=feeds)
    candidates = sources.filter_unposted(articles, posted_links)
    # 「やさしい」ソースの記事を優先的に生成する(1回の生成数には上限があるため、
    # 技術的なソースの記事ばかり選ばれて「やさしい」記事が埋もれるのを防ぐ)。
    # 各グループ内の順序(取得順)は保ったまま安定ソートする。
    candidates.sort(key=lambda a: _classify_level(a.source_domain) == "technical")

    if not candidates:
        logger.info("下書き候補となる新規記事がありませんでした。")
        if feeds is None:
            _record_run_result(got_new_articles=False)
        return

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    articles_data = _load_articles_data()
    new_entries: list[dict] = []
    attempts = 0

    for article in candidates:
        if len(new_entries) >= max_new:
            break
        if attempts >= MAX_ATTEMPTS_PER_RUN:
            logger.warning("1回の実行あたりのAPI呼び出し上限(%d件)に達したため打ち切り", MAX_ATTEMPTS_PER_RUN)
            break

        safe_link = _safe_http_url(article.link)
        if not safe_link:
            logger.warning("記事リンクがhttp/https以外のためスキップ: %r", article.link)
            state.record_posted(article.link)
            continue

        if feeds is not None and _fable_atlas_is_duplicate(article):
            logger.info("同じ話題の重複のためスキップ: %s", article.title)
            state.record_posted(article.link)
            continue

        attempts += 1
        try:
            result = generator.generate_headline_and_summary(article)
        except Exception:
            logger.exception("記事の生成に失敗したためスキップ: %s", article.link)
            continue

        slug = _make_slug(safe_link, result.get("tags"))
        image_url = _safe_http_url(sources.fetch_og_image(article.link))
        image_kind = "real" if image_url else "fallback"

        entry = {
            "slug": slug,
            "link": safe_link,
            "headline": result["headline"],
            "seo_title": result.get("seo_title") or result["headline"],
            "summary": result["summary"],
            "importance_score": result["importance_score"],
            "buzz_score": result["buzz_score"],
            "recommend_score": result["recommend_score"],
            "tldr": result["tldr"],
            "what_happened": result["what_happened"],
            "why_it_matters": result["why_it_matters"],
            "impact_on_reader": result["impact_on_reader"],
            "reader_relevance": result["reader_relevance"],
            "risk_point": result["risk_point"],
            "opportunity_point": result["opportunity_point"],
            "mot_take": result.get("mot_take") or "",
            "what_to_watch_next": result.get("what_to_watch_next") or "",
            "tags": result.get("tags") or [],
            "faq": result.get("faq") or [],
            "digest": result.get("digest") or {},
            "source": article.source,
            "image_url": image_url,
            "image_kind": image_kind,
            "level": _classify_level(article.source_domain),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        articles_data.append(entry)
        new_entries.append(entry)
        state.record_posted(article.link)
        if feeds is not None:
            _fable_atlas_record(article)
        logger.info("記事生成成功: %s -> articles/%s.html", article.link, slug)

    if not new_entries:
        logger.info("生成できた記事がありませんでした。")
        if feeds is None:
            _record_run_result(got_new_articles=False)
        return

    if feeds is None:
        _record_run_result(got_new_articles=True)

    # 関連記事を選べるよう、articles_dataが確定してから各記事ページを書き出す
    valid_topic_tags = set(_collect_topics(articles_data))
    for entry in new_entries:
        _write_article_page(entry, articles_data, valid_topic_tags)

    # 保持上限を超えたら古いものから削除(ページファイルも削除)
    if len(articles_data) > MAX_STORED_ARTICLES:
        overflow = articles_data[: len(articles_data) - MAX_STORED_ARTICLES]
        articles_data = articles_data[len(articles_data) - MAX_STORED_ARTICLES :]
        for old in overflow:
            old_path = ARTICLES_DIR / f"{old['slug']}.html"
            old_path.unlink(missing_ok=True)

    _save_articles_data(articles_data)
    _write_index_and_meta(articles_data, len(new_entries))


def _write_index_and_meta(articles_data: list[dict], new_count: int) -> None:
    # 一覧ページはサーバー側で最新MAX_INDEX_ARTICLES件を描画し、
    # それ以降(最大MAX_INFINITE_SCROLL_ARTICLES件)はJSでスクロール時に追加読み込みする
    all_latest = list(reversed(articles_data))
    initial = all_latest[:MAX_INDEX_ARTICLES]
    more = all_latest[MAX_INDEX_ARTICLES : MAX_INDEX_ARTICLES + MAX_INFINITE_SCROLL_ARTICLES]

    cards_html = []
    for entry in initial:
        thumbnail = _render_thumbnail(
            entry["image_url"], entry["image_kind"], entry["source"], entry["slug"], entry["headline"],
            for_article_page=False, tags=entry.get("tags"),
        )
        cards_html.append(
            CARD_TEMPLATE.format(
                new_badge=NEW_BADGE_HTML if _is_new(entry["generated_at"]) else "",
                thumbnail=thumbnail,
                thumb_share=_thumb_share_html(entry["slug"], entry["headline"]),
                slug=entry["slug"],
                headline=html_lib.escape(entry["headline"]),
                source=html_lib.escape(entry["source"]),
                summary=html_lib.escape(entry["summary"]),
                reading_time=_reading_time(entry),
                search_text=html_lib.escape(entry["headline"]),
                level=_entry_level(entry),
                level_badge=_level_badge(entry),
                card_tags=_render_card_tags(entry),
                ad_code=_pick_ad(entry),
                importance_class=" card-minor" if _entry_importance(entry) == "minor" else "",
            )
        )

    def _more_entry(e: dict) -> dict:
        page_url = _abs_url(f"articles/{e['slug']}.html")
        data = {
            "slug": e["slug"],
            "headline": e["headline"],
            "source": e["source"],
            "summary": e["summary"],
            "image_url": e["image_url"],
            "image_kind": e["image_kind"],
            "is_new": _is_new(e["generated_at"]),
            "share_text": urllib.parse.quote(e["headline"]),
            "share_url": urllib.parse.quote(page_url),
            "reading_time": _reading_time(e),
            "level": _entry_level(e),
            "level_label": LEVEL_LABELS[_entry_level(e)],
            "tags": (e.get("tags") or [])[:3],
            "ad_code": _pick_ad(e),
            "importance": _entry_importance(e),
        }
        if e["image_kind"] != "real":
            data["g1"], data["g2"] = _pick_gradient(e["source"])
        return data

    more_articles_json = json.dumps(
        [_more_entry(e) for e in more], ensure_ascii=False
    ).replace("</", "<\\/")  # </script>によるタグ混入対策

    # HEROは「今日一番重要なもの」を出したいので、まずmajor記事を新しい順に探し、
    # 無ければ従来通り情報の厚みベースの編集部ピックアップにフォールバックする。
    major_recent = [e for e in reversed(articles_data) if _entry_importance(e) == "major"]
    if major_recent:
        hero_entry = major_recent[0]
    else:
        hero_pool = _pick_editorial_highlights(articles_data, limit=1)
        hero_entry = hero_pool[0] if hero_pool else None
    hero_slug = hero_entry["slug"] if hero_entry else None

    topics_summary = {
        tag: {"slug": _topic_slug(tag), "latest": entries[0].get("generated_at", "")}
        for tag, entries in _collect_topics(articles_data).items()
    }
    topics_summary_json = json.dumps(topics_summary, ensure_ascii=False).replace("</", "<\\/")

    index_html = INDEX_TEMPLATE.format(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        cards="".join(cards_html),
        hero=_render_hero(hero_entry) if hero_entry else "",
        ticker=_render_ticker(articles_data, exclude_slug=hero_slug),
        todays_briefing=_render_todays_briefing(articles_data, exclude_slug=hero_slug),
        topics_explore=_render_topics_explore(articles_data),
        topics_summary_json=topics_summary_json,
        favicon=FAVICON_DATA_URI,
        page_url=_abs_url("index.html"),
        more_articles_json=more_articles_json,
        icon_x_svg_js=json.dumps(ICON_X_SVG),
        goatcounter=GOATCOUNTER_SCRIPT,
        google_verification=GOOGLE_SITE_VERIFICATION,
        csp=CSP_META,
        google_font=GOOGLE_FONT_LINK,
        theme_init=THEME_INIT_SCRIPT,
        organization_jsonld=_render_organization_jsonld(),
        site_logo=_abs_url("og-image.png"),
    )
    INDEX_PATH.write_text(index_html, encoding="utf-8")
    STYLE_PATH.write_text(STYLE_CSS, encoding="utf-8")
    SHARE_JS_PATH.write_text(SHARE_JS, encoding="utf-8")
    ABOUT_PATH.write_text(
        ABOUT_TEMPLATE.format(
            favicon=FAVICON_DATA_URI,
            goatcounter=GOATCOUNTER_SCRIPT,
            page_url=_abs_url("about.html"),
            csp=CSP_META,
            google_font=GOOGLE_FONT_LINK,
            theme_init=THEME_INIT_SCRIPT,
            nav=_render_sub_nav("", _abs_url("about.html")),
        ),
        encoding="utf-8",
    )
    CONTACT_PATH.write_text(
        CONTACT_TEMPLATE.format(
            favicon=FAVICON_DATA_URI,
            goatcounter=GOATCOUNTER_SCRIPT,
            page_url=_abs_url("contact.html"),
            csp=CSP_META,
            google_font=GOOGLE_FONT_LINK,
            theme_init=THEME_INIT_SCRIPT,
            nav=_render_sub_nav("", _abs_url("contact.html")),
        ),
        encoding="utf-8",
    )
    PRODUCTS_PATH.write_text(
        PRODUCTS_TEMPLATE.format(
            favicon=FAVICON_DATA_URI,
            goatcounter=GOATCOUNTER_SCRIPT,
            page_url=_abs_url("products.html"),
            csp=CSP_META,
            google_font=GOOGLE_FONT_LINK,
            theme_init=THEME_INIT_SCRIPT,
            nav=_render_sub_nav("", _abs_url("products.html")),
        ),
        encoding="utf-8",
    )
    topic_urls = _write_topic_pages(articles_data)
    _write_feed(articles_data)
    _write_llms_txt(articles_data)
    _write_robots_and_sitemap(articles_data, extra_urls=topic_urls)

    logger.info(
        "サイト生成完了: 新規%d件 / 一覧表示%d件 / テーマページ%d件 (%s)",
        new_count, len(cards_html), len(topic_urls), INDEX_PATH,
    )


def regenerate_all() -> None:
    """新規記事の取得なしで、既存の全記事ページ・一覧ページをテンプレート最新版で再生成する。
    広告コードやデザインを変更した後、過去記事にも反映させたい場合に使う。
    """
    articles_data = _load_articles_data()
    if not articles_data:
        logger.info("再生成対象の記事がありません。")
        return
    valid_topic_tags = set(_collect_topics(articles_data))
    for entry in articles_data:
        _write_article_page(entry, articles_data, valid_topic_tags)
    _write_index_and_meta(articles_data, 0)
    logger.info("全ページ再生成完了: %d件", len(articles_data))


def _write_article_page(entry: dict, articles_data: list[dict], valid_topic_tags: set[str] | None = None) -> None:
    thumb_for_article = _render_thumbnail(
        entry["image_url"], entry["image_kind"], entry["source"], entry["slug"], entry["headline"],
        for_article_page=True, tags=entry.get("tags"),
    )

    related_pool = _related_entries(entry, articles_data, limit=1 + MAX_RELATED_ARTICLES)
    next_insight_html = ""
    if related_pool:
        next_entry = related_pool[0]
        next_image = _safe_http_url(next_entry.get("image_url"))
        if next_image:
            image_tag = f'<img src="{html_lib.escape(next_image)}" alt="" loading="lazy">'
        else:
            image_tag = ""

        remaining = related_pool[1:]
        items_html = ""
        if remaining:
            items = "\n".join(
                RELATED_ITEM_TEMPLATE.format(slug=o["slug"], headline=html_lib.escape(o["headline"]))
                for o in remaining
            )
            items_html = f'  <ul class="insight-list">\n{items}\n  </ul>\n'

        next_insight_html = NEXT_INSIGHT_TEMPLATE.format(
            slug=next_entry["slug"],
            headline=html_lib.escape(next_entry["headline"]),
            image_tag=image_tag,
            items=items_html,
        )

    page_url = _abs_url(f"articles/{entry['slug']}.html")
    share_text = urllib.parse.quote(entry["headline"])
    share_url = urllib.parse.quote(page_url)
    # 記事に実画像が無い場合、SNS共有カードが無地にならないようMOTロゴにフォールバックする
    og_image = (_safe_http_url(entry["image_url"]) if entry["image_kind"] == "real" else "") or _abs_url("og-image.png")
    safe_link = _safe_http_url(entry["link"]) or "#"

    breadcrumb_items = [("ホーム", _abs_url("index.html"))]
    first_topic_tag = next((t for t in (entry.get("tags") or []) if t in valid_topic_tags), None)
    if first_topic_tag:
        breadcrumb_items.append((first_topic_tag, _abs_url(f"topics/{_topic_slug(first_topic_tag)}.html")))
    breadcrumb_items.append((entry["headline"], page_url))

    article_html = ARTICLE_PAGE_TEMPLATE.format(
        headline=html_lib.escape(entry["headline"]),
        seo_title=html_lib.escape(entry.get("seo_title") or entry["headline"]),
        favicon=FAVICON_DATA_URI,
        thumbnail=thumb_for_article,
        source=html_lib.escape(entry["source"]),
        level_badge=_level_badge(entry),
        generated_at=entry["generated_at"],
        body=_render_article_body(entry),
        faq=_render_faq_html(entry.get("faq")),
        summary=html_lib.escape(entry["summary"]),
        link=html_lib.escape(safe_link),
        page_url=html_lib.escape(page_url),
        og_image=html_lib.escape(og_image),
        share_text=share_text,
        share_url=share_url,
        slug=entry["slug"],
        next_insight=next_insight_html,
        ad_code=_pick_ad(entry),
        goatcounter=GOATCOUNTER_SCRIPT,
        structured_data=(
            _render_structured_data(entry, page_url, og_image)
            + "\n"
            + _render_breadcrumb_jsonld(breadcrumb_items)
        ),
        iso_published=_iso_datetime(entry["generated_at"]),
        tags=_render_tag_pills(entry, prefix="../topics/", valid_topic_tags=valid_topic_tags),
        tag_tracker=_render_tag_tracker(entry),
        csp=CSP_META,
        nav=_render_sub_nav("../", page_url),
        google_font=GOOGLE_FONT_LINK,
        theme_init=THEME_INIT_SCRIPT,
    )
    (ARTICLES_DIR / f"{entry['slug']}.html").write_text(article_html, encoding="utf-8")


_WEEKDAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS_EN = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _rfc822_datetime(generated_at: str) -> str:
    """RSS 2.0のpubDateはRFC 822形式が正式仕様(ISO 8601ではない)。"""
    try:
        dt = datetime.strptime(generated_at, "%Y-%m-%d %H:%M")
    except ValueError:
        return ""
    return (
        f"{_WEEKDAYS_EN[dt.weekday()]}, {dt.day:02d} {_MONTHS_EN[dt.month - 1]} {dt.year} "
        f"{dt.strftime('%H:%M:%S')} +0900"
    )


def _write_feed(articles_data: list[dict]) -> None:
    """サイト自体のRSSフィード(feed.xml)を書き出す。フィードリーダーで購読できるようにし、
    読者の習慣化(定期的な再訪問)を狙う。"""
    latest = list(reversed(articles_data))[:MAX_FEED_ARTICLES]
    items = []
    for e in latest:
        page_url = _abs_url(f"articles/{e['slug']}.html")
        pub_date = _rfc822_datetime(e.get("generated_at", ""))
        items.append(
            "  <item>\n"
            f"    <title>{html_lib.escape(e['headline'])}</title>\n"
            f"    <link>{html_lib.escape(page_url)}</link>\n"
            f"    <guid>{html_lib.escape(page_url)}</guid>\n"
            f"    <description>{html_lib.escape(e['summary'])}</description>\n"
            + (f"    <pubDate>{pub_date}</pubDate>\n" if pub_date else "")
            + "  </item>"
        )
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        "  <title>AI特化メディアMOT</title>\n"
        f"  <link>{html_lib.escape(_abs_url('index.html'))}</link>\n"
        "  <description>生成AI・ChatGPT・Claude最新ニュースまとめ</description>\n"
        + "\n".join(items)
        + "\n</channel></rss>\n"
    )
    FEED_PATH.write_text(feed, encoding="utf-8")


def _write_llms_txt(articles_data: list[dict]) -> None:
    """AIクローラー(LLM)向けのサイト索引。llms.txt(非公式だが普及しつつある慣習)に従い、
    記事のURL・タイトル・概要・更新日時をプレーンテキストで一覧化する。"""
    lines = [
        "# AI特化メディアMOT",
        "",
        "> AIの最新ニュースを日本語で要約・解説するメディア。RSSで集めた一次情報をもとに、"
        "編集部が見出し・要約・解説を作成しています(生成AIによる要約を含む。各記事のSOURCE/FACT表記に元記事URLを明記)。",
        "",
        f"サイトURL: {SITE_BASE_URL}/",
        f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 記事一覧",
        "",
    ]
    recent = sorted(articles_data, key=lambda e: e.get("generated_at", ""), reverse=True)[:MAX_LLMS_TXT_ARTICLES]
    for e in recent:
        url = _abs_url(f"articles/{e['slug']}.html")
        title = (e.get("seo_title") or e.get("headline") or "").replace("\n", " ")
        summary = (e.get("summary") or "").replace("\n", " ")
        updated = e.get("generated_at", "")
        source = e.get("source", "")
        lines.append(f"- [{title}]({url}): {summary} (出典: {source} / 更新: {updated})")
    LLMS_TXT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_robots_and_sitemap(articles_data: list[dict], extra_urls: list[str] | None = None) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    urls = [
        (_abs_url("index.html"), today), (_abs_url("about.html"), today),
        (_abs_url("products.html"), today), (_abs_url("contact.html"), today),
        (_abs_url("nagano/index.html"), today), (_abs_url("nagano/about.html"), today),
        (_abs_url("nagano/stories.html"), today),
    ]
    urls += [
        (_abs_url(f"articles/{e['slug']}.html"), e.get("generated_at", "")[:10] or today) for e in articles_data
    ]
    urls += [(u, today) for u in (extra_urls or [])]

    sitemap_entries = "\n".join(
        f"  <url><loc>{html_lib.escape(u)}</loc><lastmod>{lastmod}</lastmod></url>" for u, lastmod in urls
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{sitemap_entries}\n"
        "</urlset>\n"
    )
    SITEMAP_PATH.write_text(sitemap, encoding="utf-8")

    sitemap_line = f"Sitemap: {_abs_url('sitemap.xml')}\n" if SITE_BASE_URL else ""
    robots = f"User-agent: *\nAllow: /\n{sitemap_line}"
    ROBOTS_PATH.write_text(robots, encoding="utf-8")


CLAUDE_FALLBACK_TAGS = {"claude", "anthropic"}
CLAUDE_FALLBACK_IMAGE = "images/claude-fallback.png"
CLAUDE_FALLBACK_BG = "#DA7756"  # Anthropicのブランドカラー(クレイ/オレンジ)


def _render_thumbnail(
    image_url: str | None, image_kind: str | None, source: str, slug: str, headline: str, *,
    for_article_page: bool, tags: list[str] | None = None,
) -> str:
    safe_image_url = _safe_http_url(image_url)
    is_claude_related = any((t or "").strip().lower() in CLAUDE_FALLBACK_TAGS for t in (tags or []))
    if image_kind == "real" and safe_image_url:
        bg_style = ""
        img_tag = f'<img class="thumb" src="{html_lib.escape(safe_image_url)}" alt="" loading="lazy">'
    elif is_claude_related:
        # 元記事に画像が無いClaude/Anthropic関連記事は、汎用グラデーションの代わりに
        # Anthropic公式ブランドマーク(スパークロゴ)を使う(ユーザー提供の画像を使用)。
        bg_style = f"background: {CLAUDE_FALLBACK_BG};"
        img_tag = (
            f'<img class="thumb thumb-contain" src="{html_lib.escape(_abs_url(CLAUDE_FALLBACK_IMAGE))}" '
            f'alt="" loading="lazy">'
        )
    else:
        color1, color2 = _pick_gradient(source)
        bg_style = f"background: linear-gradient(135deg, {color1}, {color2});"
        img_tag = ""

    template = ARTICLE_THUMBNAIL_TEMPLATE if for_article_page else THUMBNAIL_TEMPLATE
    return template.format(
        slug=slug,
        bg_style=bg_style,
        img_tag=img_tag,
        headline=html_lib.escape(headline),
    )


if __name__ == "__main__":
    import sys

    load_dotenv(Path(__file__).parent.parent / ".env")
    try:
        if "--regenerate" in sys.argv:
            regenerate_all()
        else:
            build()
    except Exception:
        logger.exception("build_site.pyが異常終了しました")
        alert.send_alert("build_site.pyが異常終了しました", "詳細はlogs/ai_news_run.logを確認してください。")
        raise
