"""Step 1 実行スクリプト: 全20クラブ選手マスタ正規化・利き足＆Transfermarkt属性補完・名寄せ再解決."""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.player_master_enricher import run_step1_player_master_enrichment
from pipeline.tactical_position_resolver import TacticalPositionResolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("enrich_all_players_step1")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Step 1 Player Master & Dominant Foot Enrichment")
    parser.add_argument("--force-tm", action="store_true", help="Force re-fetch from Transfermarkt")
    args = parser.parse_args()

    summary = run_step1_player_master_enrichment(force_tm=args.force_tm)
    logger.info("Step 1 enrichment summary: %s", json.dumps(summary, ensure_ascii=False))

    # Re-resolve all 120 matches in player_match_positions with normalized entity_master_players
    resolver = TacticalPositionResolver()
    pos_res = resolver.resolve_all_2026_matches()
    logger.info("Position re-resolution: %s", json.dumps(pos_res, ensure_ascii=False))

    # Audit DB coverage
    conn = sqlite3.connect(ROOT_DIR / "data" / "football.db")
    try:
        total_emp = conn.execute("SELECT COUNT(*) FROM entity_master_players").fetchone()[0]
        foot_emp = conn.execute(
            "SELECT COUNT(*) FROM entity_master_players WHERE dominant_foot IS NOT NULL AND dominant_foot != ''",
        ).fetchone()[0]
        unlinked_pmp = conn.execute(
            "SELECT COUNT(*) FROM player_match_positions WHERE player_id IS NULL OR player_id = ''",
        ).fetchone()[0]
        match_players_total = conn.execute(
            "SELECT COUNT(DISTINCT player_id) FROM player_match_positions WHERE player_id IS NOT NULL AND player_id != ''",
        ).fetchone()[0]
        match_players_with_foot = conn.execute(
            """
            SELECT COUNT(DISTINCT pmp.player_id)
            FROM player_match_positions pmp
            JOIN entity_master_players emp ON pmp.player_id = emp.player_id
            WHERE emp.dominant_foot IS NOT NULL AND emp.dominant_foot != ''
            """,
        ).fetchone()[0]
        logger.info(
            "AUDIT => entity_master_players: %d (with dominant_foot: %d [%.1f%%]) | "
            "unlinked player_match_positions: %d | "
            "appeared players with dominant_foot: %d/%d [%.1f%%]",
            total_emp,
            foot_emp,
            (foot_emp / total_emp * 100.0) if total_emp else 0.0,
            unlinked_pmp,
            match_players_with_foot,
            match_players_total,
            (match_players_with_foot / match_players_total * 100.0) if match_players_total else 0.0,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()

