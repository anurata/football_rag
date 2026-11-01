"""Comprehensive validation of estimated xG and xA metrics across all players.

Performs objective statistical and domain-specific checks:
1. Pearson and Spearman correlations with real goals and assists.
2. Positional breakdown of per-90 metrics (FW, MF, DF, GK).
3. Team-level consistency between summed player xG and official team xG.
4. Top performer leaderboard verification.
5. Outlier and anomaly screening.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"


def load_player_season_aggregates(
    db_path: Path = DEFAULT_DB_PATH,
    min_minutes: int = 270,
) -> pd.DataFrame:
    """Loads season aggregate metrics for players meeting minimum minutes threshold."""
    conn = sqlite3.connect(db_path)
    query = """
        SELECT
            player_name,
            team_id,
            position,
            COUNT(*) AS matches_count,
            SUM(minutes_played) AS total_minutes,
            SUM(goals) AS total_goals,
            SUM(assists) AS total_assists,
            SUM(xg) AS total_xg,
            SUM(xa) AS total_xa
        FROM player_match_stats
        GROUP BY player_name, team_id
        HAVING total_minutes >= ?
    """
    df = pd.read_sql_query(query, conn, params=(min_minutes,))
    conn.close()

    # Calculate per-90 rates
    df["xg90"] = (df["total_xg"] / df["total_minutes"]) * 90.0
    df["xa90"] = (df["total_xa"] / df["total_minutes"]) * 90.0
    df["goals90"] = (df["total_goals"] / df["total_minutes"]) * 90.0
    df["assists90"] = (df["total_assists"] / df["total_minutes"]) * 90.0

    return df


def calculate_statistical_correlations(
    df: pd.DataFrame,
) -> Dict[str, float]:
    """Calculates Pearson and Spearman correlations for goals vs xG and assists vs xA."""
    pearson_goals_xg = float(df["total_goals"].corr(df["total_xg"], method="pearson"))
    # Spearman rank correlation without external scipy dependency
    spearman_goals_xg = float(df["total_goals"].rank().corr(df["total_xg"].rank()))

    pearson_assists_xa = float(df["total_assists"].corr(df["total_xa"], method="pearson"))
    spearman_assists_xa = float(df["total_assists"].rank().corr(df["total_xa"].rank()))

    # Also per-90 rate correlations
    pearson_goals90_xg90 = float(df["goals90"].corr(df["xg90"], method="pearson"))
    pearson_assists90_xa90 = float(df["assists90"].corr(df["xa90"], method="pearson"))

    return {
        "pearson_goals_xg": round(pearson_goals_xg, 4),
        "spearman_goals_xg": round(spearman_goals_xg, 4),
        "pearson_assists_xa": round(pearson_assists_xa, 4),
        "spearman_assists_xa": round(spearman_assists_xa, 4),
        "pearson_goals90_xg90": round(pearson_goals90_xg90, 4),
        "pearson_assists90_xa90": round(pearson_assists90_xa90, 4),
    }


def calculate_positional_averages(
    df: pd.DataFrame,
) -> Dict[str, Dict[str, float]]:
    """Calculates average xG90, xA90, goals90, and assists90 grouped by position."""
    pos_order = ["FW", "MF", "DF", "GK"]
    result: Dict[str, Dict[str, float]] = {}

    for pos in pos_order:
        sub = df[df["position"] == pos]
        if sub.empty:
            continue
        result[pos] = {
            "player_count": len(sub),
            "avg_xg90": round(float(sub["xg90"].mean()), 3),
            "avg_xa90": round(float(sub["xa90"].mean()), 3),
            "avg_goals90": round(float(sub["goals90"].mean()), 3),
            "avg_assists90": round(float(sub["assists90"].mean()), 3),
            "avg_total_xg": round(float(sub["total_xg"].mean()), 2),
            "avg_total_xa": round(float(sub["total_xa"].mean()), 2),
        }

    return result


def check_team_total_consistency(
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Verifies that the sum of player xG matches team xG in each match."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            tms.match_id,
            tms.team_id,
            tms.xg AS official_team_xg,
            COALESCE(SUM(pms.xg), 0.0) AS player_sum_xg
        FROM team_match_stats tms
        LEFT JOIN player_match_stats pms
            ON tms.match_id = pms.match_id AND tms.team_id = pms.team_id
        WHERE tms.xg IS NOT NULL
        GROUP BY tms.match_id, tms.team_id
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"match_count": 0, "avg_diff": 0.0, "max_diff": 0.0}

    diffs = [abs(r[2] - r[3]) for r in rows]
    return {
        "match_count": len(rows),
        "mean_absolute_difference": round(float(np.mean(diffs)), 4),
        "max_absolute_difference": round(float(np.max(diffs)), 4),
        "perfect_match_ratio": round(float(np.mean([d < 0.05 for d in diffs])), 4),
    }


def get_top_performers(
    df: pd.DataFrame,
    top_n: int = 15,
) -> Dict[str, List[Dict[str, Any]]]:
    """Extracts top performers in xG and xA for qualitative sanity checking."""
    top_xg_df = df.sort_values(by="total_xg", ascending=False).head(top_n)
    top_xa_df = df.sort_values(by="total_xa", ascending=False).head(top_n)

    top_xg = []
    for _, r in top_xg_df.iterrows():
        top_xg.append({
            "name": r["player_name"],
            "team": r["team_id"],
            "pos": r["position"],
            "xg": round(float(r["total_xg"]), 2),
            "goals": int(r["total_goals"]),
            "xg90": round(float(r["xg90"]), 2),
            "minutes": int(r["total_minutes"]),
        })

    top_xa = []
    for _, r in top_xa_df.iterrows():
        top_xa.append({
            "name": r["player_name"],
            "team": r["team_id"],
            "pos": r["position"],
            "xa": round(float(r["total_xa"]), 2),
            "assists": int(r["total_assists"]),
            "xa90": round(float(r["xa90"]), 2),
            "minutes": int(r["total_minutes"]),
        })

    return {
        "top_xg": top_xg,
        "top_xa": top_xa,
    }


def detect_anomalies(
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Detects anomalies such as negative values, excessive single-match xG, etc."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) FROM player_match_stats
        WHERE xg < 0.0 OR xa < 0.0
    """)
    negative_count = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM player_match_stats
        WHERE xg > 2.5
    """)
    extreme_xg_count = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM player_match_stats
        WHERE position = 'GK' AND xg > 0.05
    """)
    gk_high_xg_count = cur.fetchone()[0]

    conn.close()

    return {
        "negative_values_count": negative_count,
        "extreme_single_match_xg_over_2_5": extreme_xg_count,
        "gk_with_unreasonable_xg": gk_high_xg_count,
    }


def run_full_validation_report(
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Runs all validation modules and compiles a comprehensive audit report."""
    df = load_player_season_aggregates(db_path)
    correlations = calculate_statistical_correlations(df)
    positional = calculate_positional_averages(df)
    consistency = check_team_total_consistency(db_path)
    top_performers = get_top_performers(df, top_n=15)
    anomalies = detect_anomalies(db_path)

    return {
        "analyzed_players_count": len(df),
        "correlations": correlations,
        "positional_breakdown": positional,
        "team_consistency": consistency,
        "anomalies": anomalies,
        "top_performers": top_performers,
    }


if __name__ == "__main__":
    report = run_full_validation_report()
    print("=== xG / xA Objective Validation Report ===")
    print(f"Total analyzed players (>=270 mins): {report['analyzed_players_count']}")
    print("\n[1. Correlations]")
    for k, v in report["correlations"].items():
        print(f"  {k}: {v}")
    print("\n[2. Positional Averages (per 90 min)]")
    for pos, vals in report["positional_breakdown"].items():
        print(f"  {pos:2s} ({vals['player_count']:3d} players): xG90={vals['avg_xg90']:.3f}, Goals90={vals['avg_goals90']:.3f} | xA90={vals['avg_xa90']:.3f}, Assists90={vals['avg_assists90']:.3f}")
    print("\n[3. Team Total Consistency]")
    print(f"  Matches checked: {report['team_consistency']['match_count']}")
    print(f"  Mean absolute difference: {report['team_consistency']['mean_absolute_difference']}")
    print(f"  Max absolute difference: {report['team_consistency']['max_absolute_difference']}")
    print("\n[4. Anomaly Screening]")
    for k, v in report["anomalies"].items():
        print(f"  {k}: {v}")
    print("\n[5. Top 15 xG Performers]")
    for r in report["top_performers"]["top_xg"]:
        print(f"  {r['name']} ({r['team']}, {r['pos']}): Goals={r['goals']}, xG={r['xg']:.2f}, xG90={r['xg90']:.2f}")
    print("\n[6. Top 15 xA Performers]")
    for r in report["top_performers"]["top_xa"]:
        print(f"  {r['name']} ({r['team']}, {r['pos']}): Assists={r['assists']}, xA={r['xa']:.2f}, xA90={r['xa90']:.2f}")
