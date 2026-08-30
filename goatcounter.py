"""GoatCounter(アクセス解析)のAPIから統計データを取得する。

読み取り専用のAPIトークン(GOATCOUNTER_API_TOKEN環境変数)を使う。
取得失敗(トークン未設定・ネットワーク障害等)はサイト生成自体を止めたくないため、
例外を投げずNoneを返す。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta

API_BASE = "https://mottainai.goatcounter.com/api/v0"


def _get(path: str, timeout: int = 15) -> dict | None:
    token = os.environ.get("GOATCOUNTER_API_TOKEN")
    if not token:
        return None
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


def fetch_recent_stats(days: int = 1) -> dict | None:
    """直近days日間の合計PVとページ別上位を取得する。取得失敗時はNone。"""
    end = datetime.now()
    start = end - timedelta(days=days)
    date_range = f"start={start.strftime('%Y-%m-%d')}&end={end.strftime('%Y-%m-%d')}"

    total = _get(f"/stats/total?{date_range}")
    hits = _get(f"/stats/hits?{date_range}&limit=10")
    if total is None or hits is None:
        return None

    return {
        "total_pv": total.get("total", 0),
        "top_pages": [
            {"path": h.get("path", ""), "count": h.get("count", 0)}
            for h in hits.get("hits", [])
            if h.get("path")
        ],
    }
