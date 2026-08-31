import json
import html
from pathlib import Path

DATA_PATH = Path(r"C:\Users\kodama\AppData\Local\Temp\claude\c--Users-kodama-Desktop-claude-ryuu\440679aa-7300-4f66-8a3b-05117bc98e3a\scratchpad\social_preview_data.json")
OUT_PATH = Path(r"C:\Users\kodama\AppData\Local\Temp\claude\c--Users-kodama-Desktop-claude-ryuu\440679aa-7300-4f66-8a3b-05117bc98e3a\scratchpad\social_preview.html")

data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

ANGLE_COLORS = {
    "fear": "#e0574f",
    "surprise": "#d99a2b",
    "opportunity": "#3d9a6b",
    "practical": "#4c6ef5",
}

def esc(s):
    return html.escape(s or "")

tabs = []
panels = []
for i, a in enumerate(data["angles"]):
    color = ANGLE_COLORS.get(a["type"], "#888")
    active = " active" if i == 0 else ""
    tabs.append(
        f'<button class="tab{active}" style="--c:{color}" data-idx="{i}" onclick="showPanel({i})">{esc(a["label"])}</button>'
    )
    imgs = "".join(
        f'<img src="data:image/jpeg;base64,{b64}" alt="slide {j+1}">'
        for j, b64 in enumerate(a["images"])
    )
    panels.append(f"""
    <section class="panel{' active' if i == 0 else ''}" id="panel-{i}" style="--c:{color}">
      <div class="slides">{imgs}</div>
      <div class="meta">
        <p class="hook">{esc(a['hook']).replace(chr(10), '<br>')}</p>
        <div class="field"><span class="k">CTA</span><p>{esc(a['cta']).replace(chr(10), '<br>')}</p></div>
        <div class="field"><span class="k">Instagram</span><p>{esc(a['caption_instagram']).replace(chr(10), '<br>')}</p></div>
        <div class="field"><span class="k">Facebook</span><p>{esc(a['caption_facebook']).replace(chr(10), '<br>')}</p></div>
        <div class="field"><span class="k">TikTok</span><p>{esc(a['caption_tiktok']).replace(chr(10), '<br>')}</p></div>
        <div class="field"><span class="k">YouTube Shorts</span><p>{esc(a['caption_youtube']).replace(chr(10), '<br>')}</p></div>
        <div class="field"><span class="k">X</span><p>{esc(a['x_post']).replace(chr(10), '<br>')}</p></div>
      </div>
    </section>
    """)

html_doc = f"""<title>SNS投稿プレビュー</title>
<style>
:root {{
  --bg: #f6f5f2; --surface: #ffffff; --ink: #1c1b1a; --sub: #6b6863; --line: #e4e1da;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{ --bg:#151412; --surface:#1e1c19; --ink:#efece6; --sub:#a39d92; --line:#332f2a; }}
}}
:root[data-theme="dark"] {{ --bg:#151412; --surface:#1e1c19; --ink:#efece6; --sub:#a39d92; --line:#332f2a; }}
* {{ box-sizing: border-box; }}
body {{
  background: var(--bg); color: var(--ink); margin: 0;
  font-family: "Hiragino Sans", "Yu Gothic", system-ui, sans-serif;
  padding: 28px 20px 80px;
}}
.wrap {{ max-width: 880px; margin: 0 auto; }}
h1 {{ font-size: 1.15rem; margin: 0 0 4px; }}
.sub {{ color: var(--sub); font-size: 0.85rem; margin: 0 0 20px; }}
.tabs {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
.tab {{
  border: 1px solid var(--line); background: var(--surface); color: var(--ink);
  padding: 8px 16px; border-radius: 999px; font-size: 0.85rem; cursor: pointer;
}}
.tab.active {{ background: var(--c); border-color: var(--c); color: #fff; }}
.panel {{ display: none; }}
.panel.active {{ display: block; }}
.slides {{
  display: flex; gap: 10px; overflow-x: auto; padding-bottom: 10px; margin-bottom: 18px;
  border-bottom: 3px solid var(--c);
}}
.slides img {{ width: 150px; border-radius: 8px; flex-shrink: 0; display: block; }}
.meta {{ background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; }}
.hook {{ font-size: 1.05rem; font-weight: 700; margin: 0 0 14px; line-height: 1.5; }}
.field {{ margin-bottom: 14px; padding-bottom: 14px; border-bottom: 1px solid var(--line); }}
.field:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
.field .k {{ display: inline-block; font-size: 0.72rem; color: var(--c); font-weight: 700; letter-spacing: 0.04em; margin-bottom: 4px; }}
.field p {{ margin: 0; font-size: 0.88rem; line-height: 1.7; color: var(--ink); }}
</style>
<div class="wrap">
  <h1>{esc(data['headline'])}</h1>
  <p class="sub">slug: {esc(data['slug'])} / social_score: {data['social_score']} / importance_score: {data['importance_score']}</p>
  <div class="tabs">{''.join(tabs)}</div>
  {''.join(panels)}
</div>
<script>
function showPanel(idx) {{
  document.querySelectorAll('.panel').forEach((p, i) => p.classList.toggle('active', i === idx));
  document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', i === idx));
}}
</script>
"""

OUT_PATH.write_text(html_doc, encoding="utf-8")
print("wrote", OUT_PATH, len(html_doc), "chars")
