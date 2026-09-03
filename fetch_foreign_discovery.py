"""海外Tier1/2メディア(BBC/CNBC/The Verge/WIRED/MIT Technology Review)から
AI関連ニュースを探し、確認なしで自動更新する(build_site.build_foreign_discovery)。

編集を経た報道機関のみが対象。個人発信(Hacker News等)はfetch_trend_candidates.py側で
候補一覧化するのみに留め、ここでは記事化しない。
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

import alert
import build_site
from build_site import logger

if __name__ == "__main__":
    load_dotenv(Path(__file__).parent.parent / ".env")
    try:
        build_site.build_foreign_discovery(max_new=2)
    except Exception:
        logger.exception("fetch_foreign_discovery.pyが異常終了しました")
        alert.send_alert(
            "fetch_foreign_discovery.pyが異常終了しました",
            "詳細はlogs/foreign_discovery_run.logを確認してください。",
        )
        raise
