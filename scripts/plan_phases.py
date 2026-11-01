"""
フェーズ判定CLI (scripts/plan_phases.py)

日程をクロールし、現在時刻（JST）で「今実行すべき試合とフェーズ」を JSON 出力する。
GitHub Actions のポーリング型ジョブから呼ばれる想定。

使い方:
  python scripts/plan_phases.py --year 2026 [--now 2026-10-31T18:00] [--schedule-html file.html]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from pipeline.phase_calculator import (
    JST,
    PREVIEW_DRAFT,
    PREVIEW_FINAL,
    done_phases_from_stage,
    plan_matches,
)
from scrapers.schedule_crawler import ScheduleCrawler

EXPORTS_DIR = ROOT_DIR / "exports"


def load_stage_map(db_path: str = DEFAULT_DB_PATH) -> Dict[str, int]:
    """DB から match_id -> source_updated_stage を取得する。"""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT match_id, source_updated_stage FROM matches",
        ).fetchall()
    finally:
        conn.close()
    return {row[0]: row[1] or 0 for row in rows}


def detect_preview_done(match_id: str, exports_dir: Path = EXPORTS_DIR) -> Set[str]:
    """exports/ のファイル有無から preview 系の完了を判定する。"""
    done: Set[str] = set()
    draft_names = (f"{match_id}_preview_auto.md", f"{match_id}_preview.md")
    if any((exports_dir / name).exists() for name in draft_names):
        done.add(PREVIEW_DRAFT)
    notebooklm_dir = exports_dir / "notebooklm"
    if notebooklm_dir.exists() and any(notebooklm_dir.glob(f"{match_id}*")):
        done.add(PREVIEW_FINAL)
    return done


def build_done_lookup(
    matches: List[dict],
    stage_map: Dict[str, int],
    exports_dir: Path = EXPORTS_DIR,
) -> Dict[str, Set[str]]:
    """各試合の完了済みフェーズ集合を構築する。"""
    lookup: Dict[str, Set[str]] = {}
    for match in matches:
        match_id = match.get("match_id", "")
        done = done_phases_from_stage(stage_map.get(match_id))
        done |= detect_preview_done(match_id, exports_dir)
        lookup[match_id] = done
    return lookup


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase planner (KO-relative)")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--start-mw", type=int, default=1)
    parser.add_argument("--end-mw", type=int, default=38)
    parser.add_argument("--now", type=str, default=None, help="ISO8601 (JST). 省略時は現在時刻")
    parser.add_argument("--schedule-html", type=str, default=None)
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now).replace(tzinfo=JST) if args.now else datetime.now(JST)
    html = None
    if args.schedule_html:
        html = Path(args.schedule_html).read_text(encoding="utf-8")

    crawler = ScheduleCrawler()
    matches = crawler.build_schedule(
        html_content=html,
        year=args.year,
        start_mw=args.start_mw,
        end_mw=args.end_mw,
    )
    done_lookup = build_done_lookup(matches, load_stage_map(args.db))
    plan = plan_matches(matches, now, done_lookup)
    print(json.dumps({"now": now.isoformat(), "plan": plan}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

