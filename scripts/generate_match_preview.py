# -*- coding: utf-8 -*-
"""
Generate Match Preview CLI (scripts/generate_match_preview.py).
Deterministically extracts facts and formats the match preview report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.preview_fact_extractor import PreviewFactExtractor
from pipeline.preview_markdown_formatter import format_preview_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate match preview report.")
    parser.add_argument("--home", default="OKA", help="Home team ID")
    parser.add_argument("--away", default="FCT", help="Away team ID")
    parser.add_argument("--date", default="2026-10-31", help="Match date")
    parser.add_argument("--matchweek", type=int, default=13, help="Matchweek")
    parser.add_argument("--output", default="exports/20261031_OKA_FCT_preview.md", help="Output file path")
    args = parser.parse_args()

    extractor = PreviewFactExtractor()
    facts = extractor.extract_match_preview_facts(
        home_team_id=args.home,
        away_team_id=args.away,
        match_date=args.date,
        matchweek=args.matchweek,
    )

    report_md = format_preview_markdown(facts)

    out_path = ROOT_DIR / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md, encoding="utf-8")
    print(f"Match preview successfully written to: {out_path}")


if __name__ == "__main__":
    main()

