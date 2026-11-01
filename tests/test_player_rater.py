"""
tests/test_player_rater.py

Unit tests for PlayerRatingGenerator ensuring real player loading,
high-fidelity narrative comments, and consistent rating mathematics.
"""

import unittest
from agent.player_rater import PlayerRatingGenerator


class TestPlayerRatingGenerator(unittest.TestCase):
    """Test suite for PlayerRatingGenerator."""

    def setUp(self) -> None:
        """Initialize rater with existing SQLite football.db."""
        self.rater = PlayerRatingGenerator(db_path="data/football.db")

    def test_real_player_ratings_for_fixture(self) -> None:
        """Verify real player names and stats are loaded instead of dummy placeholders."""
        summary = {
            "match": {
                "match_id": "20261025_FCT_MIT",
                "home_team_id": "FCT",
                "away_team_id": "MIT",
                "home_score": 6,
                "away_score": 0,
            },
            "events": [],
        }

        res = self.rater.generate_match_ratings(summary)
        self.assertIn("home_players", res)
        self.assertIn("away_players", res)
        self.assertIn("mom", res)

        home_players = res["home_players"]
        self.assertGreaterEqual(len(home_players), 10)

        # Check real player names exist
        player_names = [p["name"] for p in home_players]
        self.assertIn("安斎 颯馬", player_names)
        self.assertIn("キム スンギュ", player_names)

        # Verify NO dummy placeholders exist
        for p in home_players:
            self.assertNotIn("守護神 (GK)", p["name"])
            self.assertNotIn("右サイドバック", p["name"])
            self.assertNotIn("守備的ボランチ", p["name"])
            self.assertGreater(p["rating"], 0)
            self.assertGreater(len(p["comment"]), 10)

    def test_rating_mathematics_clamping(self) -> None:
        """Verify rating calculations are strictly within [4.5, 8.5]."""
        rate_win = self.rater._calculate_player_rating(
            base_rating=6.5,
            goals=3,
            assists=2,
            pos="FW",
            conceded=0,
            score=5,
            minutes=90,
            is_starter=True,
        )
        self.assertLessEqual(rate_win, 8.5)
        self.assertGreaterEqual(rate_win, 7.5)

        rate_loss = self.rater._calculate_player_rating(
            base_rating=5.5,
            goals=0,
            assists=0,
            pos="DF",
            conceded=5,
            score=0,
            minutes=90,
            is_starter=True,
        )
        self.assertGreaterEqual(rate_loss, 4.5)
        self.assertLessEqual(rate_loss, 5.5)

    def test_comment_generation_handles_goals(self) -> None:
        """Verify comment properly mentions goals and assists."""
        cmt = self.rater._generate_player_comment(
            pname="安斎 颯馬",
            pos="MF",
            goals=2,
            assists=0,
            minutes=90,
            is_starter=True,
            conceded=0,
            score=3,
        )
        self.assertIn("2ゴール", cmt)


if __name__ == "__main__":
    unittest.main()

