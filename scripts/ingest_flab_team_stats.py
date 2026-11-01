# -*- coding: utf-8 -*-
"""
Football LAB チームスタッツ一括インジェスト実行スクリプト (scripts/ingest_flab_team_stats.py).

全120試合（全20クラブ）の Football LAB 生データから、インターセプト、CK、クロス、
タックル、CBP等の詳細スタッツを `data/football.db` の `team_match_flab_stats` テーブルに格納する。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.flab_team_stats_ingester import ingest_all_flab_team_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ingest_flab_team_stats")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Football LAB team stats into SQLite DB.",
    )
    parser.add_argument(
        "--db-path",
        default=str(ROOT_DIR / "data" / "football.db"),
        help="Path to target football.db",
    )
    parser.add_argument(
        "--flab-dir",
        default=str(ROOT_DIR / "data" / "raw" / "football_lab"),
        help="Path to directory containing football_lab raw JSON files",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    flab_dir = Path(args.flab_dir)

    logger.info("Starting Football LAB team stats ingestion...")
    logger.info("  DB Path: %s", db_path)
    logger.info("  Raw Dir: %s", flab_dir)

    result = ingest_all_flab_team_stats(db_path=db_path, flab_dir=flab_dir)
    logger.info("Ingestion completed: %s", result)


if __name__ == "__main__":
    main()
