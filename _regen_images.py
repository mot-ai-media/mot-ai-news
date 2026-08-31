import json
from pathlib import Path
import social_visuals as sv

BASE = Path(__file__).parent
queue = json.loads((BASE / "social_queue.json").read_text(encoding="utf-8"))
slug, item = list(queue.items())[0]
tags = item.get("tags", [])

for angle in item["angles"]:
    atype = angle["type"]
    sv.make_hook_slide(tags, angle["hook"], atype, slug)
    sv.make_carousel_slides(angle["carousel"], atype, slug, tags)
    sv.make_cta_slide(slug, angle.get("cta"), atype)
    print("regenerated:", atype)
