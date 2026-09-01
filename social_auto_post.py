"""タスクスケジューラから1日3回(7時/11時/19時)呼ばれる自動投稿スクリプト。

ルール:
- 1日の投稿上限は2回。3つの時間枠のうち、承認済みコンテンツがある枠でだけ投稿し、
  既に本日2回投稿済みならスキップする。
- 対象はsocial_queue.jsonでstatusが"approved"の記事のみ(承認は今まで通り、
  social_review.htmlで内容確認したうえで手動でstatusを書き換える運用)。
- 使うangleは、記事側に"approved_angle"の指定があればそれを使う。無指定なら
  "surprise"をデフォルトにする(過去の実投稿2件とも、この角度が最も反応が素直だった)。
- 実際の投稿・GitHubへのpush等の処理本体はsocial_publish.pyを再利用する(重複実装しない)。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

from social_publish import SOCIAL_QUEUE_PATH, PublishError, publish_to_instagram

DEFAULT_ANGLE = "surprise"
DAILY_POST_LIMIT = 3


def _today_published_count(queue: dict) -> int:
    today = date.today().isoformat()
    count = 0
    for item in queue.values():
        published_at = item.get("published_at", "")
        if item.get("status") == "published" and published_at.startswith(today):
            count += 1
    return count


def main() -> None:
    load_dotenv(Path(__file__).parent.parent / ".env")

    queue = json.loads(SOCIAL_QUEUE_PATH.read_text(encoding="utf-8"))

    already_today = _today_published_count(queue)
    if already_today >= DAILY_POST_LIMIT:
        print(f"[{datetime.now()}] 本日は既に{already_today}回投稿済み(上限{DAILY_POST_LIMIT}回)のためスキップします。")
        return

    candidate_slug = next((slug for slug, item in queue.items() if item.get("status") == "approved"), None)
    if not candidate_slug:
        # 1日3投稿を確実にするため、承認待ちが無い場合はsocial_score最高のdraftを自動承認する。
        # (以前は手動承認が無いとスキップしていたが、それだと投稿が滞る事故が実際に起きたため)
        draft_candidates = [(slug, item) for slug, item in queue.items() if item.get("status") == "draft"]
        if not draft_candidates:
            print(f"[{datetime.now()}] 承認済み・下書きともにコンテンツが無いためスキップします。social_content.pyで新規生成してください。")
            return
        candidate_slug, item = max(draft_candidates, key=lambda x: x[1].get("social_score", 0))
        item["status"] = "approved"
        queue[candidate_slug] = item
        SOCIAL_QUEUE_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{datetime.now()}] 承認待ちが無かったため自動承認しました: {candidate_slug}")

    item = queue[candidate_slug]
    angle = item.get("approved_angle", DEFAULT_ANGLE)

    print(f"[{datetime.now()}] 投稿します: {candidate_slug} / angle={angle}")
    try:
        result = publish_to_instagram(candidate_slug, angle, live=True)
        print(f"[{datetime.now()}] 投稿成功: {result}")
    except PublishError as e:
        print(f"[{datetime.now()}] 投稿失敗: {e}")


if __name__ == "__main__":
    main()
