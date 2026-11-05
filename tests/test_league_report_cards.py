# -*- coding: utf-8 -*-
"""
Tests for Matchweek Report Cards (J1番記者通信簿 節別一覧).
(tests/test_league_report_cards.py)
"""

import unittest
from pipeline.league_overview_data import get_matchweek_report_cards
from views.league_view import _load_matchweek_report_cards


class TestLeagueReportCards(unittest.TestCase):
    """Test suite for matchweek-level 20-team report cards aggregation."""

    def setUp(self) -> None:
        self.season = 2026

    def test_get_matchweek_report_cards(self) -> None:
        """Verify report cards aggregation for all 20 clubs in an active matchweek."""
        res = get_matchweek_report_cards(season=self.season)

        self.assertIn("season", res)
        self.assertIn("matchweek", res)
        self.assertIn("team_cards", res)
        self.assertIn("match_pairs", res)

        team_cards = res["team_cards"]
        match_pairs = res["match_pairs"]

        # In 2026 season, active MW has 20 clubs across 10 matches
        self.assertEqual(len(team_cards), 20)
        self.assertEqual(len(match_pairs), 10)

        # Check rankings order (sorted by total_score DESC)
        scores = [t["total_score"] for t in team_cards]
        self.assertEqual(scores, sorted(scores, reverse=True))

        # Check fields of each team card
        for idx, card in enumerate(team_cards, start=1):
            self.assertEqual(card["week_rank"], idx)
            self.assertIn("team_id", card)
            self.assertIn("team_name", card)
            self.assertIn("rank", card)
            self.assertIn("total_score", card)
            self.assertIn("critique", card)
            self.assertIn("headline", card["critique"])
            self.assertIn("text", card["critique"])
            self.assertIn("metrics", card)
            self.assertEqual(len(card["metrics"]), 6)

        # Check match pairs structure
        for pair in match_pairs:
            self.assertIn("match_id", pair)
            self.assertIn("home", pair)
            self.assertIn("away", pair)
            self.assertTrue(pair["home"]["is_home"])
            self.assertFalse(pair["away"]["is_home"])

    def test_cached_loader(self) -> None:
        """Verify cached Streamlit loader executes properly."""
        data = _load_matchweek_report_cards(season=self.season, matchweek=13)
        self.assertIsNotNone(data)
        self.assertEqual(data.get("matchweek"), 13)
        self.assertEqual(len(data.get("team_cards", [])), 20)


if __name__ == "__main__":
    unittest.main()
