"""
Unit tests for pipeline database schema, models, and constraints.
"""

import sqlite3
import unittest
from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    MatchBundleModel,
)
from pipeline.db import init_db


class TestDatabaseSchema(unittest.TestCase):
    """Test SQLite schema initialization and CRUD operations in memory."""

    def setUp(self):
        # Use in-memory SQLite database for testing
        self.conn = init_db(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_tables_created(self):
        """Verify all expected tables are created."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        expected_tables = [
            "matches",
            "team_match_stats",
            "player_match_stats",
            "match_events",
            "match_reviews",
            "entity_master_teams",
            "entity_master_players",
        ]
        for tbl in expected_tables:
            self.assertIn(tbl, tables, f"Table {tbl} was not created.")

    def test_insert_match_and_stats(self):
        """Test inserting a match and associated team stats."""
        cursor = self.conn.cursor()

        # Insert match
        cursor.execute(
            """
            INSERT INTO matches (
                match_id, season, matchweek, date, home_team_id, away_team_id,
                home_score, away_score, stadium, weather
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "20261021_FCT_KAS",
                2026,
                34,
                "2026-10-21",
                "FCT",
                "KAS",
                2,
                1,
                "味の素スタジアム",
                "晴",
            ),
        )

        # Insert team stats
        cursor.execute(
            """
            INSERT INTO team_match_stats (
                match_id, team_id, period, possession, xg, shots, total_distance_km
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            ("20261021_FCT_KAS", "FCT", "ALL", 52.4, 1.85, 14, 115.3),
        )

        self.conn.commit()

        # Query back
        cursor.execute("SELECT * FROM matches WHERE match_id = ?", ("20261021_FCT_KAS",))
        match_row = cursor.fetchone()
        self.assertIsNotNone(match_row)
        self.assertEqual(match_row["home_score"], 2)
        self.assertEqual(match_row["away_team_id"], "KAS")

        cursor.execute("SELECT * FROM team_match_stats WHERE match_id = ?", ("20261021_FCT_KAS",))
        stats_row = cursor.fetchone()
        self.assertIsNotNone(stats_row)
        self.assertAlmostEqual(stats_row["possession"], 52.4)

    def test_pydantic_model_validation(self):
        """Test validation and serialization of Pydantic models."""
        match = MatchModel(
            match_id="20261021_FCT_KAS",
            season=2026,
            matchweek=34,
            date="2026-10-21",
            home_team_id="FCT",
            away_team_id="KAS",
            home_score=2,
            away_score=1,
            stadium="味の素スタジアム",
            weather="晴",
        )
        self.assertEqual(match.match_id, "20261021_FCT_KAS")

        event = MatchEventModel(
            event_id="EV_20261021_FCT_KAS_01",
            match_id="20261021_FCT_KAS",
            minute=34,
            period="1H",
            game_state="DRAW",
            team_id="FCT",
            player_name="ディエゴ オリヴェイラ",
            event_type="GOAL",
            coord_x=92.5,
            coord_y=51.0,
            zone_name="ボックス内・ゴール前",
            xg=0.45,
            situation="OPEN_PLAY",
            description_text="左サイドからのグラウンダーのクロスを右足で押し込み先制。",
        )
        self.assertEqual(event.event_type, "GOAL")
        self.assertAlmostEqual(event.xg, 0.45)

        bundle = MatchBundleModel(
            match=match,
            events=[event],
        )
        self.assertEqual(len(bundle.events), 1)
        self.assertEqual(bundle.match.home_score, 2)

    def test_seed_entity_master(self):
        """Test seeding entity_master.json into SQLite database."""
        from pipeline.db import seed_entity_master

        seed_entity_master(self.conn)
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM entity_master_teams;")
        team_count = cursor.fetchone()[0]
        self.assertGreaterEqual(team_count, 20)

        cursor.execute("SELECT * FROM entity_master_teams WHERE team_id = 'FCT';")
        fct = cursor.fetchone()
        self.assertIsNotNone(fct)
        self.assertEqual(fct["canonical_name"], "FC東京")
        self.assertEqual(fct["football_lab_slug"], "tokyo")

        cursor.execute("SELECT COUNT(*) FROM entity_master_players;")
        player_count = cursor.fetchone()[0]
        self.assertGreaterEqual(player_count, 4)


if __name__ == "__main__":
    unittest.main()
