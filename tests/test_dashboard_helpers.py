"""
Unit tests for dashboard data helper functions (tests/test_dashboard_helpers.py).
"""

import unittest
from app import (
    fetch_available_matchweeks,
    fetch_matches_for_mw,
    fetch_match_reviews,
)
from pipeline.db import DEFAULT_DB_PATH


class TestDashboardHelpers(unittest.TestCase):
    def test_fetch_available_matchweeks(self):
        mws = fetch_available_matchweeks(DEFAULT_DB_PATH)
        self.assertIsInstance(mws, list)
        self.assertTrue(len(mws) > 0)
        self.assertIn(1, mws)

    def test_fetch_matches_for_mw(self):
        matches = fetch_matches_for_mw(1, DEFAULT_DB_PATH)
        self.assertIsInstance(matches, list)
        self.assertTrue(len(matches) > 0)
        first = matches[0]
        self.assertEqual(first["matchweek"], 1)
        self.assertIn("home_team_id", first)
        self.assertIn("away_team_id", first)

    def test_fetch_match_reviews(self):
        matches = fetch_matches_for_mw(1, DEFAULT_DB_PATH)
        match_id = matches[0]["match_id"]
        reviews = fetch_match_reviews(match_id, DEFAULT_DB_PATH)
        self.assertIsInstance(reviews, list)
        self.assertTrue(len(reviews) > 0)
        self.assertIn("content_text", reviews[0])


if __name__ == "__main__":
    unittest.main()
