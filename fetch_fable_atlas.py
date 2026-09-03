"""Claude FableとChatGPT Atlas関連ニュースだけを狙う専用ウォッチ。

2時間おきにタスクスケジューラから呼ばれる想定。Google News RSS(sources.FABLE_ATLAS_FEEDS)
経由で複数の実メディアを横断検索するため、出典の信頼性は通常の記事生成と同じ水準を保つ。
新しい実記事が見つからない回は何もせず終わる(記事のねつ造はしない)。
1回の実行で最大2件までに制限し、API呼び出しの暴走を防ぐ。
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

import alert
import build_site
import sources
from build_site import logger

if __name__ == "__main__":
    load_dotenv(Path(__file__).parent.parent / ".env")
    try:
        build_site.build(feeds=sources.FABLE_ATLAS_FEEDS, max_new=2)
    except Exception:
        logger.exception("fetch_fable_atlas.pyが異常終了しました")
        alert.send_alert(
            "fetch_fable_atlas.pyが異常終了しました",
            "詳細はlogs/fable_atlas_run.logを確認してください。",
        )
        raise
