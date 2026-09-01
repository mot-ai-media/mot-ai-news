"""tiktok_manual_post/ の中身から、スマホで見て手動投稿するための一覧ページを生成する。

画像はGitHubリポジトリにpush済みなので、raw.githubusercontent.com経由でそのまま
参照する(docs/への複製コピーが不要)。生成物はdocs/tiktok-queue.htmlとして
サイトの一部として公開する(検索エンジンには不要なのでnoindexにする)。
"""

from __future__ import annotations

import html
from pathlib import Path

BASE_DIR = Path(__file__).parent
MANUAL_DIR = BASE_DIR / "tiktok_manual_post"
OUT_PATH = BASE_DIR / "docs" / "tiktok-queue.html"
RAW_BASE = "https://raw.githubusercontent.com/mot-ai-media/mot-ai-news/master/tiktok_manual_post"


def build() -> None:
    if not MANUAL_DIR.exists():
        print("tiktok_manual_post/ がありません。")
        return

    cards = []
    for folder in sorted(MANUAL_DIR.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        images = sorted(folder.glob("*.png"))
        caption_path = folder / "caption.txt"
        caption = caption_path.read_text(encoding="utf-8") if caption_path.exists() else ""
        imgs_html = "".join(
            f'<img src="{RAW_BASE}/{folder.name}/{img.name}" loading="lazy">' for img in images
        )
        caption_id = f"cap-{folder.name}"
        cards.append(f"""
        <section class="card">
          <h2>{html.escape(folder.name)}</h2>
          <div class="imgs">{imgs_html}</div>
          <textarea id="{caption_id}" readonly>{html.escape(caption)}</textarea>
          <button onclick="copyCap('{caption_id}', this)">キャプションをコピー</button>
        </section>
        """)

    doc = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>TikTok投稿キュー</title>
<style>
body {{ background:#111; color:#eee; font-family:sans-serif; max-width:480px; margin:0 auto; padding:16px; }}
h1 {{ font-size:1.2rem; }}
.card {{ background:#1c1c22; border-radius:12px; padding:14px; margin-bottom:20px; }}
.card h2 {{ font-size:0.9rem; color:#999; margin:0 0 10px; word-break:break-all; }}
.imgs {{ display:flex; gap:8px; overflow-x:auto; margin-bottom:10px; }}
.imgs img {{ width:140px; border-radius:8px; flex-shrink:0; }}
textarea {{ width:100%; height:70px; background:#111; color:#eee; border:1px solid #333; border-radius:8px; padding:8px; box-sizing:border-box; }}
button {{ margin-top:8px; width:100%; padding:10px; border:none; border-radius:8px; background:#2563EB; color:#fff; font-size:0.9rem; }}
</style></head>
<body>
<h1>TikTok投稿キュー({len(cards)}件)</h1>
<p style="color:#888;font-size:0.8rem;">画像を長押しで保存 → キャプションをコピー → TikTokアプリに手動投稿</p>
{''.join(cards)}
<script>
function copyCap(id, btn) {{
  var el = document.getElementById(id);
  el.select();
  navigator.clipboard.writeText(el.value).then(function() {{
    var orig = btn.textContent;
    btn.textContent = 'コピーしました!';
    setTimeout(function() {{ btn.textContent = orig; }}, 1500);
  }});
}}
</script>
</body></html>"""
    OUT_PATH.write_text(doc, encoding="utf-8")
    print(f"生成完了: {OUT_PATH} ({len(cards)}件)")


if __name__ == "__main__":
    build()
