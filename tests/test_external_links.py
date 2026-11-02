# -*- coding: utf-8 -*-
"""
tests/test_external_links.py

Unit tests for 4 major external links generator (pipeline/external_links.py).
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from pipeline.external_links import (
    generate_match_external_links,
    get_club_official_review_url,
    get_football_lab_url,
    get_yahoo_soccer_url,
    get_youtube_highlight_url,
)


class TestExternalLinks(unittest.TestCase):
    """Test suite for match external links generator."""

    def setUp(self) -> None:
        self.sample_match: Dict[str, Any] = {
            "match_id": "20261031_OKA_FCT",
            "season": 2026,
            "matchweek": 13,
            "date": "2026-10-31",
            "home_team_id": "OKA",
            "away_team_id": "FCT",
            "home_score": 0,
            "away_score": 4,
        }

    def test_youtube_highlight_url_generation(self) -> None:
        """Test YouTube highlight search URL containing match specifics."""
        url = get_youtube_highlight_url(self.sample_match)
        self.assertTrue(url.startswith("https://www.youtube.com/results?search_query="))
        self.assertIn("2026", url)
        self.assertIn("J1", url)

    def test_club_official_review_urls(self) -> None:
        """Test official URLs for both OKA and FCT."""
        fct_url = get_club_official_review_url("FCT")
        oka_url = get_club_official_review_url("OKA")
        self.assertIn("fctokyo.co.jp", fct_url)
        self.assertIn("fagiano-okayama.com", oka_url)

    def test_yahoo_and_football_lab_urls(self) -> None:
        """Test Yahoo soccer and Football LAB URLs."""
        yahoo_url = get_yahoo_soccer_url(self.sample_match)
        self.assertEqual(yahoo_url, "https://soccer.yahoo.co.jp/jleague/category/j1")

        fl_oka = get_football_lab_url("OKA")
        fl_fct = get_football_lab_url("FCT")
        self.assertIn("football-lab.jp/okay/", fl_oka)
        self.assertIn("football-lab.jp/toky/", fl_fct)

    def test_generate_match_external_links_structure(self) -> None:
        """Test complete 4 major links dict structure."""
        links = generate_match_external_links(self.sample_match)
        self.assertIn("youtube_highlights", links)
        self.assertIn("home_official_review", links)
        self.assertIn("away_official_review", links)
        self.assertIn("yahoo_soccer", links)
        self.assertIn("football_lab", links)

        # Check badge and URL validity
        yt = links["youtube_highlights"]
        self.assertEqual(yt["icon"], "📺")
        self.assertTrue(yt["url"].startswith("https://www.youtube.com"))

        home = links["home_official_review"]
        self.assertEqual(home["team_id"], "OKA")
        self.assertIn("fagiano-okayama.com", home["url"])

        away = links["away_official_review"]
        self.assertEqual(away["team_id"], "FCT")
        self.assertIn("fctokyo.co.jp", away["url"])


if __name__ == "__main__":
    unittest.main()

