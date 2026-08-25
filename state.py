"""ローカルJSONファイルでの掲載済み記事管理（重複掲載防止）。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_PATH = Path(__file__).parent / "posted_articles.json"
RETENTION_DAYS = 30


def _load() -> list[dict]:
    if not STATE_PATH.exists():
        return []
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict]) -> None:
    STATE_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def get_posted_links() -> set[str]:
    return {e["link"] for e in _load() if "link" in e}


def record_posted(link: str) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)

    entries = [e for e in _load() if datetime.fromisoformat(e["notified_at"]) > cutoff]
    entries.append({"link": link, "notified_at": now.isoformat()})
    _save(entries)
