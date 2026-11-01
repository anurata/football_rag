"""Clean up mock matches and enrich real player match metrics (avg_x, avg_y, xG, xA).

1. Purges all unplayed / mock matches (such as MW13 20261101_*) from SQLite.
2. Extracts and normalizes pitch average coordinates (avg_x, avg_y) from Yahoo formation snapshots.
3. Computes individual expected goals (xG) and expected assists (xA) matching team totals.
4. Updates player_match_stats across all matches for all 20 teams.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_YAHOO_DIR = ROOT_DIR / "data" / "raw" / "yahoo"


def clean_name_key(name: str) -> str:
    """Normalizes player name by stripping all spaces and dots."""
    return re.sub(r"[\s\u3000・\.]+", "", name or "")


def purge_mock_matches(
    db_path: Path = DEFAULT_DB_PATH,
    pattern: str = "20261101%",
) -> int:
    """Purges test / mock matches and related child records from SQLite."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    tables = [
        "player_match_stats",
        "player_match_positions",
        "match_formations",
        "team_match_stats",
        "match_events",
        "match_reviews",
        "matches",
    ]

    total_deleted = 0
    for tbl in tables:
        cur.execute(f"DELETE FROM {tbl} WHERE match_id LIKE ?", (pattern,))
        total_deleted += cur.rowcount

    conn.commit()
    conn.close()
    return total_deleted


def normalize_yahoo_coord(x: float, y: float) -> Tuple[float, float]:
    """Converts Yahoo pitch coordinates (-150..+150, -100..+100) to 0..100 scale."""
    norm_x = round(max(0.0, min(100.0, (x + 150.0) / 3.0)), 1)
    norm_y = round(max(0.0, min(100.0, (y + 100.0) / 2.0)), 1)
    return norm_x, norm_y


def parse_yahoo_match_positions(
    summary_path: Path,
) -> Dict[str, Tuple[float, float]]:
    """Extracts average normalized (x, y) coordinates for each player in a match."""
    if not summary_path.exists():
        return {}

    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    snapshots = data.get("formation_snapshots") or []
    player_points: Dict[str, List[Tuple[float, float]]] = {}

    for snap in snapshots:
        players = (snap.get("home_players") or []) + (snap.get("away_players") or [])
        for p in players:
            raw_name = p.get("player_name") or p.get("short_name")
            px = p.get("x")
            py = p.get("y")
            if raw_name and px is not None and py is not None:
                k = clean_name_key(raw_name)
                player_points.setdefault(k, []).append((float(px), float(py)))

    avg_coords: Dict[str, Tuple[float, float]] = {}
    for k, pts in player_points.items():
        if pts:
            mean_x = sum(pt[0] for pt in pts) / len(pts)
            mean_y = sum(pt[1] for pt in pts) / len(pts)
            avg_coords[k] = normalize_yahoo_coord(mean_x, mean_y)

    return avg_coords


def compute_player_xg_xa_weights(
    row: Dict[str, Any],
) -> Tuple[float, float]:
    """Computes relative weights for distributing xG and xA to a player."""
    raw_str = row.get("raw_stats_json")
    raw_data = json.loads(raw_str) if raw_str else {}

    spaia = raw_data.get("spaia") or {}
    yahoo = raw_data.get("yahoo") or {}
    cbp = raw_data.get("cbp") or {}

    shoots = float(yahoo.get("shoots") or spaia.get("shoot_count") or spaia.get("Shoot") or 0.0)
    on_target = float(yahoo.get("shoots_on_target") or spaia.get("ShootOnTarget") or 0.0)
    pa_entries = float(spaia.get("pa_entries") or spaia.get("PAPlayCount") or 0.0)
    goals = float(row.get("goals") or 0.0)
    cbp_shoot = float(cbp.get("shoot") or 0.0)

    # xG weight
    xg_weight = (
        (on_target * 3.0) +
        (max(0.0, shoots - on_target) * 0.8) +
        (pa_entries * 0.4) +
        (cbp_shoot * 1.5) +
        (goals * 3.5)
    )

    # xA weight
    assists = float(row.get("assists") or 0.0)
    through_passes = float(yahoo.get("through_passes") or 0.0)
    crosses = float(spaia.get("cross_count") or yahoo.get("crosses") or 0.0)
    at_passes = float(yahoo.get("attacking_third_passes") or spaia.get("opp_area_pass_count") or 0.0)
    cbp_pass = float(cbp.get("pass") or 0.0)
    cbp_cross = float(cbp.get("cross") or 0.0)

    xa_weight = (
        (assists * 4.0) +
        (through_passes * 2.5) +
        (crosses * 1.0) +
        (at_passes * 0.05) +
        ((cbp_pass + cbp_cross) * 0.5)
    )

    return max(0.0, xg_weight), max(0.0, xa_weight)


def distribute_team_metrics(
    team_xg: Optional[float],
    player_rows: List[Dict[str, Any]],
) -> List[Tuple[float, float]]:
    """Calculates individual xG and xA distributed per player matching match totals."""
    weights = [compute_player_xg_xa_weights(r) for r in player_rows]
    total_xg_weight = sum(w[0] for w in weights)
    total_xa_weight = sum(w[1] for w in weights)

    target_xg = float(team_xg) if team_xg is not None and team_xg > 0 else (
        sum(float(r.get("goals") or 0.0) for r in player_rows) * 0.65 + 0.5
    )
    # Estimated team expected assists pool (~75% of team xG)
    target_xa = target_xg * 0.75

    results: List[Tuple[float, float]] = []
    for (xg_w, xa_w), r in zip(weights, player_rows):
        goals = float(r.get("goals") or 0.0)
        assists = float(r.get("assists") or 0.0)

        # Calculate xG
        if total_xg_weight > 0 and xg_w > 0:
            calc_xg = (xg_w / total_xg_weight) * target_xg
            if goals > 0:
                calc_xg = max(calc_xg, goals * 0.35)
        elif goals > 0:
            calc_xg = goals * 0.45
        else:
            calc_xg = 0.0

        # Calculate xA
        if total_xa_weight > 0 and xa_w > 0:
            calc_xa = (xa_w / total_xa_weight) * target_xa
            if assists > 0:
                calc_xa = max(calc_xa, assists * 0.30)
        elif assists > 0:
            calc_xa = assists * 0.35
        else:
            calc_xa = 0.0

        results.append((round(calc_xg, 2), round(calc_xa, 2)))

    return results


def enrich_all_matches_in_db(
    db_path: Path = DEFAULT_DB_PATH,
    yahoo_dir: Path = DEFAULT_YAHOO_DIR,
) -> Dict[str, int]:
    """Enriches all matches in DB with coordinates and xG/xA."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Fetch all distinct match_ids
    cur.execute("SELECT DISTINCT match_id FROM player_match_stats ORDER BY match_id")
    match_ids = [r[0] for r in cur.fetchall()]

    updated_count = 0
    matches_processed = 0

    for match_id in match_ids:
        # Load Yahoo coordinates
        summary_path = yahoo_dir / f"{match_id}_summary.json"
        coords_map = parse_yahoo_match_positions(summary_path)

        # Fetch team xGs
        cur.execute(
            "SELECT team_id, xg FROM team_match_stats WHERE match_id = ?",
            (match_id,),
        )
        team_xgs = {r["team_id"]: r["xg"] for r in cur.fetchall()}

        # Fetch players for this match grouped by team
        cur.execute(
            """
            SELECT id, player_name, team_id, goals, assists, position, raw_stats_json
            FROM player_match_stats
            WHERE match_id = ?
            ORDER BY team_id, id
            """,
            (match_id,),
        )
        p_rows = [dict(r) for r in cur.fetchall()]
        if not p_rows:
            continue

        teams = set(r["team_id"] for r in p_rows)
        for tid in teams:
            team_players = [r for r in p_rows if r["team_id"] == tid]
            team_xg = team_xgs.get(tid)
            metrics = distribute_team_metrics(team_xg, team_players)

            for p_dict, (calc_xg, calc_xa) in zip(team_players, metrics):
                p_key = clean_name_key(p_dict["player_name"])
                coord = coords_map.get(p_key)
                avg_x = coord[0] if coord else None
                avg_y = coord[1] if coord else None

                cur.execute(
                    """
                    UPDATE player_match_stats
                    SET avg_x = ?, avg_y = ?, xg = ?, xa = ?
                    WHERE id = ?
                    """,
                    (avg_x, avg_y, calc_xg, calc_xa, p_dict["id"]),
                )
                updated_count += 1

        matches_processed += 1

    conn.commit()
    conn.close()

    return {
        "matches_processed": matches_processed,
        "rows_updated": updated_count,
    }


def run_full_cleanup_and_enrichment() -> Dict[str, Any]:
    """Full execution: Purge mock data, then compute & enrich coordinates, xG, xA."""
    print("Purging mock data (pattern: 20261101%)...")
    deleted_rows = purge_mock_matches()
    print(f"Purged {deleted_rows} mock records from database.")

    print("Enriching avg_x, avg_y, xG, and xA across all matches...")
    result = enrich_all_matches_in_db()
    print(
        f"Enrichment completed: {result['matches_processed']} matches processed, "
        f"{result['rows_updated']} player stat rows updated.",
    )
    return {
        "deleted_rows": deleted_rows,
        "enrichment": result,
    }


if __name__ == "__main__":
    run_full_cleanup_and_enrichment()
