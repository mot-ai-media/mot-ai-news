import json, base64, io
from pathlib import Path
from PIL import Image

BASE = Path(__file__).parent
queue = json.loads((BASE / "social_queue.json").read_text(encoding="utf-8"))
slug, item = list(queue.items())[0]

ANGLE_LABELS = {"fear": "不安・危機感", "surprise": "驚き・好奇心", "opportunity": "機会", "practical": "実用"}
SUFFIXES = [("hook", "1"), ("slide2", "2"), ("slide3", "3"), ("cta", "4")]

data = {"slug": slug, "headline": item["headline"], "social_score": item.get("social_score"),
        "importance_score": item.get("importance_score"), "angles": []}

for angle in item["angles"]:
    atype = angle["type"]
    imgs = []
    for suf, num in SUFFIXES:
        p = BASE / "social_assets" / f"{slug}_{atype}_{suf}.png"
        if p.exists():
            im = Image.open(p).convert("RGB")
            w = 360
            h = int(im.height * (w / im.width))
            im = im.resize((w, h), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            imgs.append(b64)
    data["angles"].append({
        "type": atype,
        "label": ANGLE_LABELS.get(atype, atype),
        "hook": angle.get("hook", ""),
        "cta": angle.get("cta", ""),
        "caption_instagram": angle.get("caption_instagram", ""),
        "caption_facebook": angle.get("caption_facebook", ""),
        "caption_tiktok": angle.get("caption_tiktok", ""),
        "caption_youtube": angle.get("caption_youtube", ""),
        "x_post": angle.get("x_post", ""),
        "images": imgs,
    })

out = Path(r"C:\Users\kodama\AppData\Local\Temp\claude\c--Users-kodama-Desktop-claude-ryuu\440679aa-7300-4f66-8a3b-05117bc98e3a\scratchpad\social_preview_data.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
total_kb = sum(len(a["images"][i]) for a in data["angles"] for i in range(len(a["images"]))) / 1024
print("wrote", out, "approx base64 KB:", round(total_kb))
