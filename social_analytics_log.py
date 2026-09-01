"""PCログオン時に、MOTの主要指標をGoogleフォーム経由でスプレッドシートに自動記録する。

Google Sheets APIの認証設定(サービスアカウント等)を避けるため、
Googleフォームのformresponse送信エンドポイントに直接POSTする方式を使う
(フォームの回答は自動的に紐づいたスプレッドシートに1行追加される)。
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
FORM_ID = "1FAIpQLSfAzWoclcrAzM1hxUFM8uRPLLR0mhPw6QHLWyY8X7vcd5Pfwg"
FORM_URL = f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse"

ENTRY_IDS = {
    "date": "entry.1864190385",
    "pv": "entry.989890539",
    "unique": "entry.2129541008",
    "peak_hour": "entry.1922903206",
    "top_ref": "entry.891295197",
    "top_article": "entry.628767803",
    "new_articles": "entry.1186523670",
    "total_articles": "entry.1710722338",
    "instagram_posts": "entry.291523072",
}


def _goatcounter_today() -> dict:
    import os
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR.parent / ".env")
    token = os.environ.get("GOATCOUNTER_API_TOKEN")
    if not token:
        return {"pv": "-", "peak_hour": "-", "top_article": "-"}

    end = datetime.now()
    start = end - timedelta(days=1)
    date_range = f"start={start.strftime('%Y-%m-%d')}&end={end.strftime('%Y-%m-%d')}"

    def get(path):
        req = urllib.request.Request(
            f"https://mottainai.goatcounter.com/api/v0{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        total = get(f"/stats/total?{date_range}")
        hits = get(f"/stats/hits?{date_range}&limit=1")
    except Exception:
        return {"pv": "-", "peak_hour": "-", "top_article": "-"}

    pv = total.get("total", "-")
    peak_hour = "-"
    today_str = end.strftime("%Y-%m-%d")
    for day_stat in total.get("stats", []):
        if day_stat.get("day") == today_str:
            hourly = day_stat.get("hourly", [])
            if hourly:
                peak_hour = f"{hourly.index(max(hourly))}時台"
            break

    top_article = "-"
    hit_list = hits.get("hits", [])
    if hit_list:
        top_article = _headline_for_path(hit_list[0].get("path", ""))

    return {"pv": pv, "peak_hour": peak_hour, "top_article": top_article}


def _headline_for_path(path: str) -> str:
    """GoatCounterのpath(例: /mot-ai-news/articles/xxx-slug.html)から、
    articles_data.jsonの見出しを引いて先頭部分だけ返す。見つからなければpathをそのまま返す。"""
    slug = Path(path).stem
    if not slug or slug == "index":
        return "トップページ"
    data_path = BASE_DIR / "articles_data.json"
    if not data_path.exists():
        return path
    articles = json.loads(data_path.read_text(encoding="utf-8"))
    for a in articles:
        if a.get("slug") == slug:
            headline = a.get("headline", "")
            return headline[:20] + ("…" if len(headline) > 20 else "")
    return path


def _article_counts() -> dict:
    path = BASE_DIR / "articles_data.json"
    if not path.exists():
        return {"new_articles": "-", "total_articles": "-"}
    articles = json.loads(path.read_text(encoding="utf-8"))
    total = len(articles)
    cutoff = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    new_count = sum(1 for a in articles if a.get("generated_at", "") >= cutoff)
    return {"new_articles": new_count, "total_articles": total}


def _instagram_today_count() -> int:
    path = BASE_DIR / "social_queue.json"
    if not path.exists():
        return 0
    queue = json.loads(path.read_text(encoding="utf-8"))
    today_str = date.today().isoformat()
    return sum(
        1 for item in queue.values()
        if item.get("status") == "published" and item.get("published_at", "").startswith(today_str)
    )


def collect_and_submit() -> None:
    gc = _goatcounter_today()
    ac = _article_counts()
    ig_count = _instagram_today_count()

    values = {
        "date": date.today().isoformat(),
        "pv": gc["pv"],
        "unique": "-",  # GoatCounter APIから信頼できる値が取れず未対応
        "peak_hour": gc["peak_hour"],
        "top_ref": "-",  # 同上、流入元エンドポイントは今後対応
        "top_article": gc["top_article"],
        "new_articles": ac["new_articles"],
        "total_articles": ac["total_articles"],
        "instagram_posts": ig_count,
    }

    payload = {ENTRY_IDS[k]: str(v) for k, v in values.items()}
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(FORM_URL, data=data, headers={"User-Agent": "Mozilla/5.0"})
    try:
        urllib.request.urlopen(req, timeout=15)
        print(f"[{datetime.now()}] 記録完了: {values}")
    except Exception as e:
        print(f"[{datetime.now()}] 記録失敗: {e}")


if __name__ == "__main__":
    collect_and_submit()
