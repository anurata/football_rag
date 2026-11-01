# -*- coding: utf-8 -*-
"""
Curate Match Review CLI (scripts/curate_match_review.py).
Interactive or deterministic CLI for collaborative post-match review curation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import get_db_connection
from pipeline.review_curation_service import ReviewCurationService


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Collaborative review curation tool with Fact/Inference separation."
    )
    parser.add_argument("--match-id", default="", help="Match ID (e.g. 20261031_OKA_FCT)")
    parser.add_argument("--home", default="", help="Home team ID (e.g. OKA)")
    parser.add_argument("--away", default="", help="Away team ID (e.g. FCT)")
    parser.add_argument("--date", default="", help="Match date (YYYY-MM-DD)")
    parser.add_argument(
        "--output",
        default="",
        help="Path to output curated Markdown file (default: exports/{match_id}_review_curated.md)",
    )
    parser.add_argument(
        "--selections",
        default="",
        help="JSON string of branch selections, e.g. '{\"deciding_factor\":\"A\",\"tactical_evaluation\":\"A\"}'",
    )
    parser.add_argument(
        "--insights",
        default="",
        help="Custom tactical insight note to append",
    )
    parser.add_argument(
        "--dump-branches",
        action="store_true",
        help="Print branches in JSON and exit (for agent skill integration)",
    )
    return parser.parse_args()


def resolve_match_id(
    match_id: str,
    home: str,
    away: str,
    date: str,
) -> Optional[str]:
    """Resolve match_id from explicit ID or team/date lookup."""
    if match_id:
        return match_id

    conn = get_db_connection()
    cursor = conn.cursor()

    if home and away:
        if date:
            cursor.execute(
                "SELECT match_id FROM matches WHERE home_team_id = ? AND away_team_id = ? AND date = ? LIMIT 1",
                (home, away, date),
            )
        else:
            cursor.execute(
                "SELECT match_id FROM matches WHERE home_team_id = ? AND away_team_id = ? ORDER BY date DESC LIMIT 1",
                (home, away),
            )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    # Fallback to latest finished match
    cursor.execute(
        "SELECT match_id FROM matches WHERE home_score IS NOT NULL ORDER BY date DESC, match_id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def main() -> None:
    """Run collaborative review curation CLI."""
    args = parse_arguments()
    service = ReviewCurationService()

    resolved_match_id = resolve_match_id(
        match_id=args.match_id,
        home=args.home,
        away=args.away,
        date=args.date,
    )

    if not resolved_match_id:
        print("Error: Could not resolve a valid match_id. Please specify --match-id or --home and --away.")
        sys.exit(1)

    workspace = service.generate_curation_workspace(match_id=resolved_match_id)

    if getattr(args, "dump_branches", False):
        print(json.dumps(workspace["branches"], ensure_ascii=False, indent=2))
        return

    facts = workspace["facts"]
    branches = workspace["branches"]

    selections_dict: Dict[str, str] = {}
    if args.selections:
        try:
            raw_sel = json.loads(args.selections)
            for branch in branches:
                bid = branch["branch_id"]
                opt_id = raw_sel.get(bid, "A")
                matched = next(
                    (opt for opt in branch["options"] if opt["option_id"] == opt_id),
                    branch["options"][0],
                )
                selections_dict[branch["title"]] = (
                    f"**選択案 [{matched['option_id']}] {matched['label']}**\n"
                    f"- {matched['fact_basis']}\n"
                    f"- {matched['inference']}"
                )
        except Exception as e:
            print(f"Warning: Failed to parse --selections JSON ({e}). Falling back to default A options.")

    if not selections_dict:
        # Default fallback to Option A for all branches
        for branch in branches:
            opt = branch["options"][0]
            selections_dict[branch["title"]] = (
                f"**選択案 [{opt['option_id']}] {opt['label']}**\n"
                f"- {opt['fact_basis']}\n"
                f"- {opt['inference']}"
            )

    curated_md = service.compile_curated_report(
        facts=facts,
        selections=selections_dict,
        custom_insights=args.insights if args.insights else None,
    )

    output_path = (
        Path(args.output)
        if args.output
        else ROOT_DIR / "exports" / f"{resolved_match_id}_review_curated.md"
    )
    service.save_curated_report(output_path, curated_md)
    print(f"Successfully generated curated match review: {output_path}")


if __name__ == "__main__":
    main()

