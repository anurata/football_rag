"""
Execute Tactical Enrichment for FC Tokyo 2026 Matches.
Updates data/structured/*_tactical.json and SQLite DB.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.tactical_enricher import enrich_match_file, update_db_events


def run_fct_enrichment():
    md_dir = ROOT_DIR / "data" / "markdown" / "2026"
    out_dir = ROOT_DIR / "data" / "structured"
    out_dir.mkdir(parents=True, exist_ok=True)

    fct_files = sorted(
        [
            f for f in md_dir.glob("*.md")
            if "FCT" in f.name and not f.name.endswith("_fctokyo.md")
        ]
    )

    print(f"Found {len(fct_files)} FC Tokyo match markdown files.")

    success_count = 0
    total_events_updated = 0

    for md_path in fct_files:
        print(f"Processing: {md_path.name}...")
        structured_data = enrich_match_file(md_path, out_dir)
        events = structured_data.get("key_tactical_events", [])

        # Convert to event dict for DB
        db_events = []
        for ev in events:
            db_events.append(
                {
                    "minute": ev["minute"],
                    "period": ev["period"],
                    "team_id": structured_data["home_team_id"] if ev["team_side"] == "HOME" else structured_data["away_team_id"],
                    "event_type": "GOAL" if ev["category"] == "CHANCE_CREATION" else "FOUL",
                    "player_name": ev["actors"][0] if ev["actors"] else "選手",
                    "situation": "OPEN_PLAY",
                    "description_text": ev["tactical_context"],
                }
            )

        updated = update_db_events(structured_data["match_id"], db_events)
        total_events_updated += updated
        success_count += 1
        print(f" -> Saved {structured_data['match_id']}_tactical.json (DB events updated: {updated})")

    print("\n=======================================================")
    print(f"Successfully enriched {success_count}/{len(fct_files)} FC Tokyo matches.")
    print(f"Total verified events updated in DB: {total_events_updated}")
    print("=======================================================")


if __name__ == "__main__":
    run_fct_enrichment()
