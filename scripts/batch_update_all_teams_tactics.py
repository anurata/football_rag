# -*- coding: utf-8 -*-
"""
Batch Update All Teams Tactics (scripts/batch_update_all_teams_tactics.py).
Computes and persists full Layer 1 & Layer 2 (55 tactical metrics + 3 major cross-analytics)
for all 20 J1 clubs in season 2026 (MW1-12).
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import List

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from pipeline.team_55_metrics_calculator import Team55MetricsCalculator
from pipeline.team_cross_analytics import TeamCrossAnalyticsEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_all_j1_teams(db_path: Path = DEFAULT_DB_PATH) -> List[str]:
    """Retrieve distinct team IDs that have match records in season 2026."""
    conn = get_db_connection(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT team_id
        FROM team_match_flab_stats
        ORDER BY team_id ASC;
        """
    )
    teams = [row[0] for row in cur.fetchall()]
    conn.close()
    return teams


def update_team_tactics(
    team_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    export_excel: bool = True,
) -> None:
    """Calculate and persist 55 metrics and cross-analytics synthesis for a single team."""
    tid = team_id.upper()
    logger.info(f"==> Processing tactics for {tid}...")

    # 1. Calculate 55 Tactical Metrics
    calc = Team55MetricsCalculator(team_id=tid, db_path=db_path)
    metrics_55 = calc.calculate_all_matches()

    # Save 55 metrics summary JSON
    json_path = ROOT_DIR / "exports" / f"{tid.lower()}_55_tactical_metrics_summary.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(metrics_55, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"  [OK] Saved 55-metrics summary to {json_path} ({len(metrics_55)} matches)")

    # 2. Run Cross-Analytics Synthesis
    engine = TeamCrossAnalyticsEngine(team_id=tid, db_path=db_path)
    synthesis_path = ROOT_DIR / "data" / "structured" / f"{tid.lower()}_season_tactical_synthesis.json"
    engine.run_and_persist_synthesis(output_path=synthesis_path)
    logger.info(f"  [OK] Persisted season tactical synthesis to {synthesis_path}")

    # 3. Update Excel Dossier if requested
    if export_excel and metrics_55:
        df_55 = pd.DataFrame(metrics_55)
        excel_target = ROOT_DIR / "exports" / f"{tid}_Layer1_Layer2_Dossier_2026.xlsx"
        
        # Also check if exports/players/{tid}_players.xlsx exists
        player_excel = ROOT_DIR / "exports" / "players" / f"{tid}_players.xlsx"
        if player_excel.exists():
            try:
                with pd.ExcelWriter(str(player_excel), engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
                    df_55.to_excel(writer, sheet_name="L2_全55項目戦術完全指標", index=False)
                logger.info(f"  [OK] Appended L2 sheet to existing player dossier: {player_excel}")
            except Exception as e:
                logger.warning(f"  [WARN] Failed to append to {player_excel}: {e}")

        # Always save complete dossier file
        try:
            with pd.ExcelWriter(str(excel_target), engine="openpyxl") as writer:
                df_55.to_excel(writer, sheet_name="L2_全55項目戦術完全指標", index=False)
            logger.info(f"  [OK] Generated complete dossier at {excel_target}")
        except Exception as e:
            logger.warning(f"  [WARN] Failed to write {excel_target}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch update tactical analytics for all J1 teams.")
    parser.add_argument("--teams", nargs="*", default=None, help="Specific team IDs to update (e.g. ZEL KAS). Defaults to all.")
    parser.add_argument("--no-excel", action="store_true", help="Skip Excel exports for faster execution.")
    args = parser.parse_args()

    start_time = time.time()
    teams = args.teams if args.teams else get_all_j1_teams()
    logger.info(f"Starting batch tactical update for {len(teams)} teams: {teams}")

    success_count = 0
    for tid in teams:
        try:
            update_team_tactics(tid, export_excel=not args.no_excel)
            success_count += 1
        except Exception as e:
            logger.error(f"Error processing team {tid}: {e}", exc_info=True)

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"Batch update completed: {success_count}/{len(teams)} teams updated in {elapsed}s.")


if __name__ == "__main__":
    main()

