"""
Unit tests for dashboard data helper functions (tests/test_dashboard_helpers.py).
"""

import unittest
from app import (
    fetch_available_seasons,
    fetch_available_matchweeks,
    fetch_matches_for_season,
    fetch_matches_for_mw,
    fetch_match_reviews,
)
from pipeline.db import DEFAULT_DB_PATH


class TestDashboardHelpers(unittest.TestCase):
    def test_fetch_available_seasons(self):
        seasons = fetch_available_seasons(DEFAULT_DB_PATH)
        self.assertIsInstance(seasons, list)
        self.assertTrue(len(seasons) > 0)
        self.assertIn(2026, seasons)
        self.assertIn(2024, seasons)

    def test_fetch_available_matchweeks(self):
        mws_all = fetch_available_matchweeks(db_path=DEFAULT_DB_PATH)
        self.assertIsInstance(mws_all, list)
        self.assertTrue(len(mws_all) > 0)
        self.assertIn(1, mws_all)

        mws_2024 = fetch_available_matchweeks(season=2024, db_path=DEFAULT_DB_PATH)
        self.assertIn(1, mws_2024)

    def test_fetch_matches_for_season(self):
        matches_2026 = fetch_matches_for_season(2026, DEFAULT_DB_PATH)
        self.assertIsInstance(matches_2026, list)
        self.assertTrue(len(matches_2026) > 0)
        match_ids = [m["match_id"] for m in matches_2026]
        self.assertIn("20261025_FCT_MIT", match_ids)

    def test_fetch_matches_for_mw(self):
        matches = fetch_matches_for_mw(1, season=2024, db_path=DEFAULT_DB_PATH)
        self.assertIsInstance(matches, list)
        self.assertTrue(len(matches) > 0)
        first = matches[0]
        self.assertEqual(first["matchweek"], 1)
        self.assertIn("home_team_id", first)
        self.assertIn("away_team_id", first)

    def test_fetch_match_reviews(self):
        matches = fetch_matches_for_mw(1, season=2024, db_path=DEFAULT_DB_PATH)
        match_id = matches[0]["match_id"]
        reviews = fetch_match_reviews(match_id, DEFAULT_DB_PATH)
        self.assertIsInstance(reviews, list)
        self.assertTrue(len(reviews) > 0)
        self.assertIn("content_text", reviews[0])


if __name__ == "__main__":
    unittest.main()
