"""Batch exporter to export player spreadsheets for all J1 teams."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure workspace root is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Dict, List
from scripts.export_team_players_sheet import export_team_player_data

# All 20 target teams
ALL_TEAMS = [
    "CER", "FCT", "FUK", "GAM", "HIR",
    "JEF", "KAS", "KAW", "MAR", "MIT",
    "NAG", "OKA", "PUL", "REY", "SAN",
    "URA", "VER", "VOB", "VVN", "ZEL",
]


def export_all_teams(
    teams: List[str] = ALL_TEAMS,
    players_dir: Path = Path("data/players"),
) -> List[Dict[str, str]]:
    """Exports player spreadsheets and CSVs for all specified teams."""
    results = []
    print(f"Starting batch export for {len(teams)} teams...")

    for idx, team_id in enumerate(teams, start=1):
        team_json = players_dir / f"{team_id}_players.json"
        if not team_json.exists():
            print(f"[{idx}/{len(teams)}] Skipping {team_id}: JSON not found.")
            continue

        try:
            res = export_team_player_data(team_id)
            print(
                f"[{idx}/{len(teams)}] {team_id} exported: "
                f"{res['player_count']} players, "
                f"{res['match_stats_count']} match logs -> {res['excel_path']}",
            )
            results.append(res)
        except Exception as e:
            print(f"[{idx}/{len(teams)}] Error exporting {team_id}: {e}", file=sys.stderr)

    print(f"Batch export completed: {len(results)}/{len(teams)} teams successfully exported.")
    return results


if __name__ == "__main__":
    export_all_teams()
