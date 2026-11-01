# -*- coding: utf-8 -*-
"""
Full Integrity Audit Script (scripts/audit_data_integrity.py).
Verifies Layer 1 and Layer 2 data completeness across all matches, teams, and players.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def audit_matches(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Audit Layer 1 match records and structured tactical files."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT match_id, matchweek, home_team_id, away_team_id, home_score, away_score
        FROM matches
        WHERE season = 2026 AND matchweek <= 12
        ORDER BY matchweek ASC;
        """
    )
    rows = cur.fetchall()
    total_matches = len(rows)
    missing_scores = sum(1 for r in rows if r[4] is None or r[5] is None)

    # Check structured tactical JSON files for each expected match
    structured_dir = ROOT_DIR / "data" / "structured"
    missing_tactical_files = []
    missing_archetype = []

    for r in rows:
        m_id = r[0]
        t_file = structured_dir / f"{m_id}_tactical.json"
        if not t_file.exists():
            missing_tactical_files.append(m_id)
        else:
            try:
                d = json.loads(t_file.read_text(encoding="utf-8"))
                if "opponent_tactical_archetype" not in d:
                    missing_archetype.append(m_id)
            except Exception:
                missing_archetype.append(m_id)

    return {
        "season_2026_mw1_12_matches": total_matches,
        "expected_matches": 120,
        "missing_scores": missing_scores,
        "missing_tactical_files": missing_tactical_files,
        "missing_archetype_files": missing_archetype,
        "status": "PASS" if total_matches == 120 and missing_scores == 0 and len(missing_tactical_files) == 0 and len(missing_archetype) == 0 else "FAIL",
    }


def audit_team_flab_layer1(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Audit Layer 1 team match flab stats (75 items + CBP)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*), COUNT(DISTINCT team_id),
               SUM(CASE WHEN cbp_attack IS NULL OR cbp_attack = 0.0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN cbp_pass IS NULL OR cbp_pass = 0.0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN distance_m IS NULL OR distance_m = 0.0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN sprints IS NULL OR sprints = 0 THEN 1 ELSE 0 END)
        FROM team_match_flab_stats;
        """
    )
    row = cur.fetchone()
    total_records, distinct_teams, null_cbp_att, null_cbp_pass, null_dist, null_sprints = row

    # Verify each team has exactly 12 records
    cur.execute(
        """
        SELECT team_id, COUNT(*)
        FROM team_match_flab_stats
        GROUP BY team_id;
        """
    )
    counts = cur.fetchall()
    abnormal_teams = [t for t, cnt in counts if cnt != 12]

    return {
        "total_team_flab_records": total_records,
        "expected_records": 240,  # 20 teams * 12 matches
        "distinct_teams": distinct_teams,
        "abnormal_team_record_counts": abnormal_teams,
        "zero_or_null_cbp_attack": null_cbp_att,
        "zero_or_null_cbp_pass": null_cbp_pass,
        "zero_or_null_distance": null_dist,
        "zero_or_null_sprints": null_sprints,
        "status": "PASS" if total_records == 240 and distinct_teams == 20 and len(abnormal_teams) == 0 else "FAIL",
    }


def audit_player_layer1(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Audit Layer 1 player match stats and player master."""
    cur = conn.cursor()

    # Player match stats
    cur.execute(
        """
        SELECT COUNT(*), COUNT(DISTINCT player_name), COUNT(DISTINCT team_id),
               SUM(CASE WHEN is_starter = 1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN avg_x IS NOT NULL AND avg_y IS NOT NULL THEN 1 ELSE 0 END)
        FROM player_match_stats;
        """
    )
    p_row = cur.fetchone()
    total_player_logs, unique_players, teams_in_players, starter_count, coords_count = p_row

    # Player master
    cur.execute(
        """
        SELECT COUNT(*), COUNT(DISTINCT team_id)
        FROM entity_master_players;
        """
    )
    m_row = cur.fetchone()
    master_players, master_teams = m_row

    return {
        "total_player_match_logs": total_player_logs,
        "unique_players_logged": unique_players,
        "teams_in_player_stats": teams_in_players,
        "total_starter_logs": starter_count,
        "logs_with_coordinates": coords_count,
        "player_master_records": master_players,
        "player_master_teams": master_teams,
        "status": "PASS" if total_player_logs > 3000 and teams_in_players == 20 else "FAIL",
    }


def audit_layer2_artifacts(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Audit Layer 2 55-metrics, cross-synthesis JSONs, and Excel dossiers."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT team_id FROM team_match_flab_stats ORDER BY team_id ASC;")
    teams = [r[0] for r in cur.fetchall()]

    exports_dir = ROOT_DIR / "exports"
    structured_dir = ROOT_DIR / "data" / "structured"
    players_excel_dir = exports_dir / "players"

    missing_55_json = []
    missing_synthesis_json = []
    missing_dossier_excel = []
    missing_player_l2_sheet = []
    metric_anomaly_count = 0

    for tid in teams:
        t_lower = tid.lower()
        t_upper = tid.upper()

        # 1. 55 metrics summary JSON
        p_55 = exports_dir / f"{t_lower}_55_tactical_metrics_summary.json"
        if not p_55.exists():
            missing_55_json.append(tid)
        else:
            try:
                data_55 = json.loads(p_55.read_text(encoding="utf-8"))
                if len(data_55) != 12:
                    metric_anomaly_count += 1
                for match_dict in data_55:
                    # Check key advanced metrics
                    for key in ["31_チーム凸包面積(㎡)", "35_タッチ関与シャノンエントロピー", "43_ポアソン期待勝点(xPTS)", "48_BPI(ボール前進総合指数)"]:
                        val = match_dict.get(key)
                        if val is None or np.isnan(val) or np.isinf(val):
                            metric_anomaly_count += 1
            except Exception:
                metric_anomaly_count += 1

        # 2. Season tactical synthesis JSON
        p_syn = structured_dir / f"{t_lower}_season_tactical_synthesis.json"
        if not p_syn.exists():
            missing_synthesis_json.append(tid)
        else:
            try:
                data_syn = json.loads(p_syn.read_text(encoding="utf-8"))
                if len(data_syn.get("time_segment_dynamics", {})) != 6:
                    metric_anomaly_count += 1
                if not data_syn.get("opponent_archetype_resistance"):
                    metric_anomaly_count += 1
            except Exception:
                metric_anomaly_count += 1

        # 3. Complete Dossier Excel
        p_dos = exports_dir / f"{t_upper}_Layer1_Layer2_Dossier_2026.xlsx"
        if not p_dos.exists():
            missing_dossier_excel.append(tid)

        # 4. Player Excel with L2 sheet
        p_ply = players_excel_dir / f"{t_upper}_players.xlsx"
        if p_ply.exists():
            try:
                xl = pd.ExcelFile(str(p_ply))
                if "L2_全55項目戦術完全指標" not in xl.sheet_names:
                    missing_player_l2_sheet.append(tid)
            except Exception:
                missing_player_l2_sheet.append(tid)

    return {
        "audited_teams_count": len(teams),
        "missing_55_summary_json": missing_55_json,
        "missing_synthesis_json": missing_synthesis_json,
        "missing_dossier_excel": missing_dossier_excel,
        "player_excel_missing_l2_sheet": missing_player_l2_sheet,
        "metric_anomalies_or_nans": metric_anomaly_count,
        "status": "PASS" if not missing_55_json and not missing_synthesis_json and not missing_dossier_excel and metric_anomaly_count == 0 else "FAIL",
    }


def main() -> None:
    conn = get_db_connection(str(DEFAULT_DB_PATH))
    conn.row_factory = sqlite3.Row

    logger.info("=== Running Full Data Integrity Audit (Layer 1 & Layer 2) ===")

    m_res = audit_matches(conn)
    t_res = audit_team_flab_layer1(conn)
    p_res = audit_player_layer1(conn)
    l2_res = audit_layer2_artifacts(conn)

    conn.close()

    report = {
        "1_matches_audit": m_res,
        "2_team_flab_layer1_audit": t_res,
        "3_player_layer1_audit": p_res,
        "4_layer2_analytics_audit": l2_res,
    }

    report_path = ROOT_DIR / "exports" / "data_integrity_audit_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("           DATA INTEGRITY AUDIT SUMMARY")
    print("=" * 60)
    print(f"1. Matches Layer 1 Status:      {m_res['status']} ({m_res['season_2026_mw1_12_matches']}/120 matches)")
    print(f"2. Team FLAB Layer 1 Status:    {t_res['status']} ({t_res['total_team_flab_records']}/240 records, 20 teams)")
    print(f"3. Players Layer 1 Status:      {p_res['status']} ({p_res['total_player_match_logs']} match logs, {p_res['player_master_records']} master records)")
    print(f"4. Layer 2 Analytics Status:    {l2_res['status']} (20 teams synthesis & 55 metrics, {l2_res['metric_anomalies_or_nans']} anomalies)")
    print("=" * 60)
    print(f"Detailed JSON report saved to: {report_path}\n")


if __name__ == "__main__":
    main()
