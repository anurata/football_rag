"""
tests/test_match_data_engine.py

Unit tests for pipeline/match_data_engine.py
"""

import unittest
from pipeline.match_data_engine import (
    fetch_match_players_with_details,
    fetch_match_timeline_events,
    fetch_match_formations,
    fetch_match_interviews_and_reviews,
)


class TestMatchDataEngine(unittest.TestCase):
    def test_fetch_players_empty(self):
        players = fetch_match_players_with_details("", "")
        self.assertEqual(players, [])

    def test_fetch_timeline_events_empty(self):
        events = fetch_match_timeline_events("")
        self.assertEqual(events, [])

    def test_fetch_formations_empty(self):
        fm = fetch_match_formations("")
        self.assertIn("home_initial", fm)
        self.assertIn("away_initial", fm)

    def test_fetch_reviews_empty(self):
        revs = fetch_match_interviews_and_reviews("")
        self.assertIn("official", revs)
        self.assertIn("home_interviews", revs)

    def test_fetch_players_real_match(self):
        # Test with real match 2026080802 if available or fallback safely
        players = fetch_match_players_with_details("2026080802", "FCT")
        if players:
            p = players[0]
            self.assertIn("player_name", p)
            self.assertIn("cbp_total", p)
            self.assertIn("photo_url", p)


if __name__ == "__main__":
    unittest.main()
