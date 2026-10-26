"""
Database cleanup and integrity verification script (scripts/clean_and_verify_db.py).
Ensures clean matchweek distributions and cleans up obsolete orphan/test records.
"""

import sys
import sqlite3
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection


def clean_obsolete_matches(db_path: str = DEFAULT_DB_PATH) -> int:
    """Remove known dummy or corrupted match entries from earlier iterations."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # Find matches where matchweek is NULL and has no team stats
    cur.execute(
        """
        SELECT m.match_id FROM matches m
        LEFT JOIN team_match_stats s ON m.match_id = s.match_id
        WHERE m.matchweek IS NULL AND s.id IS NULL;
        """,
    )
    obsolete_ids = [r[0] for r in cur.fetchall()]

    for m_id in obsolete_ids:
        cur.execute("DELETE FROM matches WHERE match_id = ?", (m_id,))

    conn.commit()
    conn.close()
    return len(obsolete_ids)


def verify_db_integrity(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Run full check on matches and child tables."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT season, matchweek, count(*)
        FROM matches
        GROUP BY season, matchweek
        ORDER BY season, matchweek;
        """,
    )
    season_mw_distribution = cur.fetchall()

    cur.execute("SELECT count(*) FROM matches;")
    total_matches = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM team_match_stats;")
    total_team_stats = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM match_reviews;")
    total_reviews = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM match_events;")
    total_events = cur.fetchone()[0]

    # Orphan checks
    cur.execute(
        """
        SELECT count(*) FROM team_match_stats
        WHERE match_id NOT IN (SELECT match_id FROM matches);
        """,
    )
    orphan_team_stats = cur.fetchone()[0]

    cur.execute(
        """
        SELECT count(*) FROM match_reviews
        WHERE match_id NOT IN (SELECT match_id FROM matches);
        """,
    )
    orphan_reviews = cur.fetchone()[0]

    cur.execute(
        """
        SELECT count(*) FROM match_events
        WHERE match_id NOT IN (SELECT match_id FROM matches);
        """,
    )
    orphan_events = cur.fetchone()[0]

    conn.close()

    return {
        "season_mw_distribution": season_mw_distribution,
        "total_matches": total_matches,
        "total_team_stats": total_team_stats,
        "total_reviews": total_reviews,
        "total_events": total_events,
        "orphans": {
            "team_stats": orphan_team_stats,
            "reviews": orphan_reviews,
            "events": orphan_events,
        },
    }


def main():
    print("=== Football DB Integrity & Cleanup Tool ===")
    cleaned_count = clean_obsolete_matches()
    print(f"Cleaned up {cleaned_count} obsolete/dummy matches.")

    report = verify_db_integrity()
    print("\nMatches distribution (Season, Matchweek, Count):")
    for row in report["season_mw_distribution"]:
        print(f" - Season {row[0]}, MW {row[1]}: {row[2]} matches")

    print(f"\nTotal matches:    {report['total_matches']}")
    print(f"Total team stats: {report['total_team_stats']}")
    print(f"Total reviews:    {report['total_reviews']}")
    print(f"Total events:     {report['total_events']}")
    print(f"Orphan records:   {report['orphans']}")
    print("============================================\n")


if __name__ == "__main__":
    main()
