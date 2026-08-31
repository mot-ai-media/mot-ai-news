"""social_queue.jsonから、レビュー用のローカルHTML一覧を生成する。

サーバー・ログイン不要。生成のたびにsocial_review.htmlを上書きし、ブラウザで直接開いて
確認する。承認/却下は今はこのファイルを見て手動判断すればよく、statusの更新も
articles_data.jsonと同じくJSONを直接編集する運用でよい(ボタンUIはまだ作らない)。
"""

from __future__ import annotations

import html
import json
from pathlib import Path

SOCIAL_QUEUE_PATH = Path(__file__).parent / "social_queue.json"
REVIEW_PATH = Path(__file__).parent / "social_review.html"
ASSETS_DIR_NAME = "social_assets"

ANGLE_LABELS = {"fear": "不安・危機感", "surprise": "驚き・好奇心", "opportunity": "機会", "practical": "実用"}
ANGLE_COLORS = {"fear": "#ef4444", "surprise": "#f59e0b", "opportunity": "#10b981", "practical": "#2563eb"}


def _slide_img(slug: str, atype: str, filename_part: str, label: str) -> str:
    path = Path(__file__).parent / ASSETS_DIR_NAME / f"{slug}_{filename_part}.png"
    if path.exists():
        return (
            f'<div style="text-align:center;"><img src="{ASSETS_DIR_NAME}/{slug}_{filename_part}.png" '
            f'style="width:130px;border-radius:8px;display:block;"><span style="font-size:11px;color:#777;">{label}</span></div>'
        )
    return (
        f'<div style="width:130px;height:230px;background:#222;border-radius:8px;'
        f'display:flex;align-items:center;justify-content:center;color:#555;font-size:11px;">{label}<br>画像なし</div>'
    )


def _angle_block(slug: str, angle: dict) -> str:
    atype = angle["type"]
    color = ANGLE_COLORS.get(atype, "#888")
    carousel = angle.get("carousel", [])

    slides_html = _slide_img(slug, atype, f"{atype}_hook", "1.hook")
    for i in range(len(carousel)):
        slides_html += _slide_img(slug, atype, f"{atype}_slide{i + 2}", f"{i + 2}")
    slides_html += _slide_img(slug, atype, f"{atype}_cta", f"{len(carousel) + 2}.CTA")

    return f"""
    <div style="border-left:4px solid {color};background:#1a1a1f;border-radius:0 10px 10px 0;padding:16px 18px;margin:12px 0;">
      <b style="color:{color};">{ANGLE_LABELS.get(atype, atype)}</b>
      <p style="color:#999;font-size:12px;margin-top:4px;">画像{len(carousel) + 2}枚のスライド投稿(1〜{len(carousel) + 2}の順)</p>
      <div style="display:flex;gap:10px;margin:10px 0;overflow-x:auto;">{slides_html}</div>
      <p><b>Hook:</b> {html.escape(angle.get('hook', ''))}</p>
      <p><b>CTA:</b> {html.escape(angle.get('cta', ''))}</p>
      <p><b>Instagram:</b> {html.escape(angle.get('caption_instagram', ''))}</p>
      <p><b>Facebook:</b> {html.escape(angle.get('caption_facebook', ''))}</p>
      <p><b>TikTok:</b> {html.escape(angle.get('caption_tiktok', ''))}</p>
      <p><b>YouTube Shorts:</b> {html.escape(angle.get('caption_youtube', ''))}</p>
      <p><b>X投稿:</b> {html.escape(angle.get('x_post', ''))}</p>
    </div>
    """


def build() -> None:
    if not SOCIAL_QUEUE_PATH.exists():
        print("social_queue.json がありません。先に social_content.py を実行してください。")
        return
    queue = json.loads(SOCIAL_QUEUE_PATH.read_text(encoding="utf-8"))
    if not queue:
        print("キューは空です。")
        return

    sections = []
    for slug, item in reversed(list(queue.items())):
        angle_blocks = "".join(_angle_block(slug, a) for a in item.get("angles", []))
        sections.append(f"""
        <section style="margin-bottom:44px;padding-bottom:28px;border-bottom:1px solid #333;">
          <h2 style="margin:0 0 6px;">{html.escape(item.get('headline', ''))}</h2>
          <p style="color:#888;font-size:13px;">
            slug: {html.escape(slug)} / social_score: {item.get('social_score', '?')} /
            importance_score: {item.get('importance_score')} /
            status: <b>{html.escape(item.get('status', ''))}</b>
          </p>
          {angle_blocks}
        </section>
        """)

    doc = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><title>MOT SNSレビュー</title>
<style>
body {{ background:#0e0e11; color:#e8e8ee; font-family:"Hiragino Sans","Yu Gothic",sans-serif;
  max-width:920px; margin:40px auto; padding:0 24px 100px; line-height:1.7; }}
h1 {{ font-size:1.5rem; }}
ul {{ margin:4px 0; padding-left:20px; font-size:0.9rem; color:#c8c8d0; }}
p {{ margin:6px 0; font-size:0.92rem; }}
</style></head>
<body>
<h1>MOT SNSコンテンツ レビュー</h1>
<p style="color:#888;">{len(queue)}件 / このページは social_review.py 実行のたびに上書きされます</p>
{''.join(sections)}
</body></html>"""
    REVIEW_PATH.write_text(doc, encoding="utf-8")
    print(f"生成完了: {REVIEW_PATH}")


if __name__ == "__main__":
    build()
