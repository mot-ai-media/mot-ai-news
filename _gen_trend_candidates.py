"""trend_candidates.json(Tier3の海外トレンド候補)から、スマホでも見やすい
一覧ページを生成する。ここに載っているのは記事化されたものではなく、
「編集者が見て判断するための下調べ」の一覧(自動公開はしない)。
"""

from __future__ import annotations

import html
from pathlib import Path

import trend_candidates

OUT_PATH = Path(__file__).parent / "docs" / "trend-candidates.html"


def build() -> None:
    entries = trend_candidates.get_all_sorted()

    cards = []
    for e in entries:
        combined = e.get("novelty_score", 0) + e.get("japan_relevance_score", 0)
        safe_link = html.escape(e["link"])
        cards.append(f"""
        <a class="card" href="{safe_link}" target="_blank" rel="noopener noreferrer">
          <div class="scores">
            <span>新規性 {e.get('novelty_score', 0)}</span>
            <span>日本未報道度 {e.get('japan_relevance_score', 0)}</span>
          </div>
          <h2>{html.escape(e['title'])}</h2>
          <p class="reason">{html.escape(e.get('reason', ''))}</p>
          <p class="meta">{html.escape(e.get('source', ''))}</p>
        </a>
        """)

    doc = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-src 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>海外トレンド候補</title>
<style>
body {{ background:#111; color:#eee; font-family:sans-serif; max-width:520px; margin:0 auto; padding:16px; }}
h1 {{ font-size:1.2rem; }}
.note {{ color:#888; font-size:0.8rem; }}
.card {{ display:block; background:#1c1c22; border-radius:12px; padding:14px; margin-bottom:14px; text-decoration:none; color:inherit; }}
.card h2 {{ font-size:1rem; margin:6px 0; }}
.scores {{ display:flex; gap:10px; font-size:0.75rem; color:#7dd3fc; }}
.reason {{ font-size:0.85rem; color:#ccc; margin:6px 0; }}
.meta {{ font-size:0.75rem; color:#888; margin:0; }}
</style></head>
<body>
<h1>海外トレンド候補({len(cards)}件)</h1>
<p class="note">Hacker Newsで話題の投稿(個人発信を含む)。自動公開はしていません。記事化したいものがあれば会話でその旨伝えてください。</p>
{''.join(cards) if cards else '<p class="note">現在候補はありません。</p>'}
</body></html>"""
    OUT_PATH.write_text(doc, encoding="utf-8")
    print(f"生成完了: {OUT_PATH} ({len(cards)}件)")


if __name__ == "__main__":
    build()
