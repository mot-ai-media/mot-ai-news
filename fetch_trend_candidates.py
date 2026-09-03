"""Hacker News(Tier3、個人発信を含む)からAI関連の話題を見つけ、
スコア付きで候補一覧(docs/trend-candidates.html)に追加する。

Tier1/2(BBC等の編集を経た報道)と違い、ここでは記事を自動生成・自動公開しない。
ユーザーが一覧を見て「これを記事にして」と判断したものだけを別途記事化する。
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

import alert
import generator
import sources
import trend_candidates
import _gen_trend_candidates
from build_site import logger

MAX_NEW_CANDIDATES_PER_RUN = 5


def run() -> None:
    seen_links = trend_candidates.get_seen_links()
    articles = sources.fetch_candidates(feeds=[sources.HN_DISCOVERY_RSS])
    new_articles = [a for a in articles if a.link not in seen_links][:MAX_NEW_CANDIDATES_PER_RUN]

    if not new_articles:
        logger.info("海外トレンド候補: 新規候補がありませんでした。")
        return

    added = 0
    for article in new_articles:
        try:
            score = generator.score_trend_candidate(article)
        except Exception:
            logger.exception("候補スコアリングに失敗したためスキップ: %s", article.link)
            continue
        trend_candidates.record_candidate(
            title=article.title,
            link=article.link,
            source="Hacker News",
            summary=article.summary,
            novelty_score=score["novelty_score"],
            japan_relevance_score=score["japan_relevance_score"],
            reason=score["one_line_reason"],
        )
        added += 1

    _gen_trend_candidates.build()
    logger.info("海外トレンド候補: %d件を新規追加しました。", added)


if __name__ == "__main__":
    load_dotenv(Path(__file__).parent.parent / ".env")
    try:
        run()
    except Exception:
        logger.exception("fetch_trend_candidates.pyが異常終了しました")
        alert.send_alert(
            "fetch_trend_candidates.pyが異常終了しました",
            "詳細はlogs/trend_candidates_run.logを確認してください。",
        )
        raise
