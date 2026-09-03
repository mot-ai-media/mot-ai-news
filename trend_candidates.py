"""Tier3(Hacker News等、個人発信を含む)の海外トレンド候補を管理する。

これらは自動で記事化しない(social_review.htmlと同じ「人が確認する」運用)。
スコア付きで一覧に残し、ユーザーが見て「これを記事にして」と指示したものだけを
記事化する想定。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_PATH = Path(__file__).parent / "trend_candidates.json"
RETENTION_DAYS = 14


def _load() -> list[dict]:
    if not STATE_PATH.exists():
        return []
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict]) -> None:
    STATE_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def get_seen_links() -> set[str]:
    return {e["link"] for e in _load() if "link" in e}


def record_candidate(
    title: str, link: str, source: str, summary: str,
    novelty_score: int, japan_relevance_score: int, reason: str,
) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    entries = [e for e in _load() if datetime.fromisoformat(e["discovered_at"]) > cutoff]
    entries.append({
        "title": title,
        "link": link,
        "source": source,
        "summary": summary,
        "novelty_score": novelty_score,
        "japan_relevance_score": japan_relevance_score,
        "reason": reason,
        "discovered_at": now.isoformat(),
    })
    _save(entries)


def get_all_sorted() -> list[dict]:
    entries = _load()
    entries.sort(
        key=lambda e: (e.get("novelty_score", 0) + e.get("japan_relevance_score", 0), e.get("discovered_at", "")),
        reverse=True,
    )
    return entries
