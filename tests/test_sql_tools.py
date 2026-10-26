"""
Unit tests for agent/sql_tools.py.
Validates SQL aggregation functions for tactical analysis and safety guards.
"""

import sqlite3
import unittest
from agent.sql_tools import TacticalSQLTools
from pipeline.db import init_db
from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchBundleModel,
)
from pipeline.indexer import MatchIndexer


class TestTacticalSQLTools(unittest.TestCase):
    """Test suite for TacticalSQLTools quantitative queries and guards."""

    def setUp(self):
        self.conn = init_db(":memory:")
        self.indexer = MatchIndexer(conn=self.conn)
        self.tools = TacticalSQLTools(conn=self.conn)
        self._seed_sample_data()

    def tearDown(self):
        self.tools.close()
        self.indexer.close()
        if self.conn:
            self.conn.close()

    def _seed_sample_data(self):
        """Seed 2 matches with comprehensive stats for testing."""
        # Match 1: FCT vs KAS (FCT 2 - 1 KAS)
        m1 = MatchModel(
            match_id="20261021_FCT_KAS",
            season=2026,
            matchweek=28,
            date="2026-10-21",
            home_team_id="FCT",
            away_team_id="KAS",
            home_score=2,
            away_score=1,
            stadium="味スタ",
            weather="晴",
            pitch_condition="良芝",
            attendance=24500,
        )

        stats1 = [
            TeamMatchStatsModel(
                match_id="20261021_FCT_KAS",
                team_id="FCT",
                period="ALL",
                game_state="ALL",
                possession=55.0,
                xg=1.85,
                shots=12,
                shots_on_target=5,
                big_chances=3,
                final_third_passes=65,
                total_distance_km=114.2,
                sprints=150,
            ),
            TeamMatchStatsModel(
                match_id="20261021_FCT_KAS",
                team_id="FCT",
                period="ALL",
                game_state="LEADING",
                possession=48.0,
                xg=0.65,
                shots=4,
                final_third_passes=20,
            ),
            TeamMatchStatsModel(
                match_id="20261021_FCT_KAS",
                team_id="KAS",
                period="ALL",
                game_state="ALL",
                possession=45.0,
                xg=0.92,
                shots=8,
                shots_on_target=3,
                big_chances=1,
                final_third_passes=40,
                total_distance_km=112.5,
                sprints=135,
            ),
        ]

        players1 = [
            PlayerMatchStatsModel(
                match_id="20261021_FCT_KAS",
                player_id="p_koki",
                player_name="小泉 慶",
                team_id="FCT",
                is_starter=True,
                minutes_played=90,
                position="MF",
                avg_x=52.0,
                avg_y=48.0,
            ),
            PlayerMatchStatsModel(
                match_id="20261021_FCT_KAS",
                player_id="p_ryotaro",
                player_name="荒木 遼太郎",
                team_id="FCT",
                is_starter=True,
                minutes_played=75,
                position="MF",
                avg_x=68.0,
                avg_y=40.0,
            ),
        ]

        events1 = [
            MatchEventModel(
                event_id="e1",
                match_id="20261021_FCT_KAS",
                minute=12,
                period="1H",
                game_state="DRAW",
                team_id="FCT",
                player_name="荒木 遼太郎",
                event_type="SHOT",
                xg=0.15,
                description_text="シュート",
            ),
            MatchEventModel(
                event_id="e2",
                match_id="20261021_FCT_KAS",
                minute=35,
                period="1H",
                game_state="DRAW",
                team_id="FCT",
                player_name="荒木 遼太郎",
                event_type="GOAL",
                xg=0.68,
                description_text="先制ゴール",
            ),
            MatchEventModel(
                event_id="e3",
                match_id="20261021_FCT_KAS",
                minute=70,
                period="2H",
                game_state="LEADING",
                team_id="FCT",
                player_name="小泉 慶",
                event_type="GOAL",
                xg=0.45,
                description_text="追加点",
            ),
        ]

        self.indexer.upsert_bundle(
            MatchBundleModel(
                match=m1,
                team_stats=stats1,
                player_stats=players1,
                events=events1,
            ),
        )

        # Match 2: FCT vs URA (URA 1 - 0 FCT) - Koizumi absent/bench
        m2 = MatchModel(
            match_id="20261028_URA_FCT",
            season=2026,
            matchweek=29,
            date="2026-10-28",
            home_team_id="URA",
            away_team_id="FCT",
            home_score=1,
            away_score=0,
            stadium="埼玉スタジアム2002",
        )

        stats2 = [
            TeamMatchStatsModel(
                match_id="20261028_URA_FCT",
                team_id="FCT",
                period="ALL",
                game_state="ALL",
                possession=42.0,
                xg=0.55,
                shots=6,
                total_distance_km=109.0,
                sprints=120,
            ),
            TeamMatchStatsModel(
                match_id="20261028_URA_FCT",
                team_id="URA",
                period="ALL",
                game_state="ALL",
                possession=58.0,
                xg=1.40,
                shots=14,
            ),
        ]

        players2 = [
            PlayerMatchStatsModel(
                match_id="20261028_URA_FCT",
                player_id="p_ryotaro",
                player_name="荒木 遼太郎",
                team_id="FCT",
                is_starter=True,
                minutes_played=90,
                position="MF",
                avg_x=62.0,
                avg_y=45.0,
            ),
            # Notice: 小泉 慶 did not play in Match 2
        ]

        self.indexer.upsert_bundle(
            MatchBundleModel(
                match=m2,
                team_stats=stats2,
                player_stats=players2,
                events=[],
            ),
        )

    def test_execute_custom_query_select(self):
        """Verify safe execution of SELECT queries."""
        rows = self.tools.execute_custom_query(
            "SELECT match_id, home_score FROM matches WHERE match_id = ?",
            ("20261021_FCT_KAS",),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["home_score"], 2)

    def test_execute_custom_query_forbidden_keywords(self):
        """Verify SQL safety guards prevent mutating statements."""
        with self.assertRaises(ValueError):
            self.tools.execute_custom_query("DROP TABLE matches;")

        with self.assertRaises(ValueError):
            self.tools.execute_custom_query("DELETE FROM matches;")

        with self.assertRaises(ValueError):
            self.tools.execute_custom_query("INSERT INTO matches VALUES ('x');")

    def test_get_match_summary(self):
        """Verify match summary retrieval."""
        summary = self.tools.get_match_summary("20261021_FCT_KAS")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["match"]["home_team_id"], "FCT")
        self.assertEqual(summary["team_stats"]["FCT"]["possession"], 55.0)
        self.assertEqual(len(summary["events"]), 3)

        none_summary = self.tools.get_match_summary("NON_EXISTING")
        self.assertIsNone(none_summary)

    def test_get_team_trajectory(self):
        """Verify chronological trajectory metrics and xG differences."""
        trajectory = self.tools.get_team_trajectory("FCT", last_n=5)
        self.assertEqual(len(trajectory), 2)

        # Match 1: FCT 2 - 1 KAS (xg: 1.85, diff: +0.15)
        m1 = trajectory[0]
        self.assertEqual(m1["match_id"], "20261021_FCT_KAS")
        self.assertEqual(m1["team_score"], 2)
        self.assertEqual(m1["team_xg"], 1.85)
        self.assertEqual(m1["xg_goal_diff"], 0.15)

        # Match 2: URA 1 - 0 FCT (FCT score: 0, xg: 0.55, diff: -0.55)
        m2 = trajectory[1]
        self.assertEqual(m2["match_id"], "20261028_URA_FCT")
        self.assertEqual(m2["team_score"], 0)
        self.assertEqual(m2["team_xg"], 0.55)
        self.assertEqual(m2["xg_goal_diff"], -0.55)

    def test_get_game_state_breakdown(self):
        """Verify game state breakdown for leading/draw stats."""
        breakdown = self.tools.get_game_state_breakdown("FCT")
        self.assertTrue(len(breakdown) >= 1)
        leading = next((b for b in breakdown if b["game_state"] == "LEADING"), None)
        self.assertIsNotNone(leading)
        self.assertEqual(leading["avg_possession"], 48.0)

    def test_get_player_impact_on_off(self):
        """Verify player on/off impact comparison (unsung hero analysis)."""
        impact = self.tools.get_player_impact_on_off("FCT", "小泉 慶")
        self.assertEqual(impact["player_name"], "小泉 慶")
        self.assertEqual(impact["on_field"]["match_count"], 1)
        self.assertEqual(impact["off_field"]["match_count"], 1)

        # In Match 1 (on), FCT won (3 pts, 2 goals, xg 1.85)
        self.assertEqual(impact["on_field"]["avg_points"], 3.0)
        self.assertEqual(impact["on_field"]["avg_xg"], 1.85)

        # In Match 2 (off), FCT lost (0 pts, 0 goals, xg 0.55)
        self.assertEqual(impact["off_field"]["avg_points"], 0.0)
        self.assertEqual(impact["off_field"]["avg_xg"], 0.55)

        self.assertEqual(impact["delta_points"], 3.0)
        self.assertEqual(impact["delta_xg"], 1.30)

    def test_get_player_pairing_stats(self):
        """Verify chemistry between two players when co-starting."""
        pair = self.tools.get_player_pairing_stats("FCT", "小泉 慶", "荒木 遼太郎")
        self.assertEqual(pair["co_starts"], 1)
        self.assertEqual(pair["team_avg_goals"], 2.0)
        self.assertIsNotNone(pair["avg_distance"])

    def test_get_timeline_phases(self):
        """Verify 15-minute phase aggregation."""
        phases = self.tools.get_timeline_phases("20261021_FCT_KAS")
        self.assertEqual(len(phases), 6)

        # Phase 0-15: e1 (minute 12, SHOT, xg 0.15)
        p1 = phases[0]
        self.assertEqual(p1["shots"], 1)
        self.assertEqual(p1["goals"], 0)
        self.assertEqual(p1["xg"], 0.15)

        # Phase 31-45: e2 (minute 35, GOAL, xg 0.68)
        p3 = phases[2]
        self.assertEqual(p3["goals"], 1)
        self.assertEqual(p3["shots"], 1)
        self.assertEqual(p3["xg"], 0.68)

        # Phase 61-75: e3 (minute 70, GOAL, xg 0.45)
        p5 = phases[4]
        self.assertEqual(p5["goals"], 1)
        self.assertEqual(p5["shots"], 1)


if __name__ == "__main__":
    unittest.main()
