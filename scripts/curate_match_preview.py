# -*- coding: utf-8 -*-
"""
Curate Match Preview CLI (scripts/curate_match_preview.py).
Interactive or deterministic CLI for collaborative preview curation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.preview_curation_service import PreviewCurationService


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Collaborative preview curation tool with Fact/Inference separation."
    )
    parser.add_argument("--home", default="OKA", help="Home team ID (e.g. OKA)")
    parser.add_argument("--away", default="FCT", help="Away team ID (e.g. FCT)")
    parser.add_argument("--date", default="2026-10-31", help="Match date (YYYY-MM-DD)")
    parser.add_argument("--matchweek", type=int, default=13, help="Matchweek number")
    parser.add_argument(
        "--output",
        default="exports/20261031_OKA_FCT_preview_curated.md",
        help="Path to output curated Markdown file",
    )
    parser.add_argument(
        "--selections",
        default="",
        help="JSON string of branch selections, e.g. '{\"lineup_home\":\"A\",\"lineup_away\":\"A\"}'",
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


def main() -> None:
    """Run collaborative preview curation CLI."""
    args = parse_arguments()
    service = PreviewCurationService()

    workspace = service.generate_curation_workspace(
        home_team_id=args.home,
        away_team_id=args.away,
        match_date=args.date,
        matchweek=args.matchweek,
    )

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

    out_file = ROOT_DIR / args.output
    service.save_curated_report(out_file, curated_md)
    print(f"Curated match preview saved successfully -> {out_file}")


if __name__ == "__main__":
    main()
