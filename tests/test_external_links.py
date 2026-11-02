# -*- coding: utf-8 -*-
"""
tests/test_external_links.py

Unit tests for direct external links generator (pipeline/external_links.py).
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from pipeline.external_links import (
    generate_match_external_links,
    get_club_official_review_url,
    get_football_lab_url,
    get_jleague_official_match_url,
    get_yahoo_soccer_url,
    get_youtube_highlight_url,
    resolve_game_id,
)


class TestExternalLinks(unittest.TestCase):
    """Test suite for direct match external links generator."""

    def setUp(self) -> None:
        self.mw13_match: Dict[str, Any] = {
            "match_id": "20261031_OKA_FCT",
            "season": 2026,
            "matchweek": 13,
            "date": "2026-10-31",
            "home_team_id": "OKA",
            "away_team_id": "FCT",
            "home_score": 0,
            "away_score": 4,
        }
        self.mw12_match: Dict[str, Any] = {
            "match_id": "20261025_FCT_MIT",
            "season": 2026,
            "matchweek": 12,
            "date": "2026-10-25",
            "home_team_id": "FCT",
            "away_team_id": "MIT",
            "home_score": 2,
            "away_score": 0,
        }

    def test_youtube_highlight_url_generation(self) -> None:
        """Test YouTube highlight search URL containing match specifics."""
        url = get_youtube_highlight_url(self.mw13_match)
        self.assertTrue(url.startswith("https://www.youtube.com/results?search_query="))
        self.assertIn("2026", url)
        self.assertIn("J1", url)
        self.assertIn("ハイライト", urllib_unquote(url))

    def test_club_official_review_urls(self) -> None:
        """Test official URLs for both OKA and FCT."""
        fct_url = get_club_official_review_url("FCT")
        oka_url = get_club_official_review_url("OKA")
        self.assertIn("fctokyo.co.jp", fct_url)
        self.assertIn("fagiano-okayama.com", oka_url)

    def test_game_id_resolution(self) -> None:
        """Verify game_id is resolved for both MW13 manual map and MW12 file map."""
        gid_13 = resolve_game_id(self.mw13_match)
        self.assertEqual(gid_13, "2026103109")

        gid_12 = resolve_game_id(self.mw12_match)
        self.assertEqual(gid_12, "2026102505")

    def test_yahoo_soccer_direct_match_url(self) -> None:
        """Test Yahoo soccer generates direct match summary URL."""
        url_13 = get_yahoo_soccer_url(self.mw13_match)
        self.assertEqual(
            url_13,
            "https://soccer.yahoo.co.jp/jleague/category/j1/game/2026103109/summary",
        )

        url_12 = get_yahoo_soccer_url(self.mw12_match)
        self.assertEqual(
            url_12,
            "https://soccer.yahoo.co.jp/jleague/category/j1/game/2026102505/summary",
        )

    def test_jleague_official_direct_match_url(self) -> None:
        """Test J-League official generates direct match URL."""
        url_13 = get_jleague_official_match_url(self.mw13_match)
        self.assertEqual(url_13, "https://www.jleague.jp/match/j1/2026/103109/")

        url_12 = get_jleague_official_match_url(self.mw12_match)
        self.assertEqual(url_12, "https://www.jleague.jp/match/j1/2026/102505/")

    def test_football_lab_direct_match_url(self) -> None:
        """Test Football LAB generates direct match report URL with date."""
        fl_oka = get_football_lab_url("OKA", self.mw13_match)
        self.assertEqual(
            fl_oka,
            "https://www.football-lab.jp/okay/report/?year=2026&month=10&date=31",
        )

        fl_fct = get_football_lab_url("FCT", self.mw12_match)
        self.assertEqual(
            fl_fct,
            "https://www.football-lab.jp/fctk/report/?year=2026&month=10&date=25",
        )

    def test_football_lab_fallback_when_no_match(self) -> None:
        """Test Football LAB fallback to club top page when match is None."""
        fl_top = get_football_lab_url("FCT", None)
        self.assertEqual(fl_top, "https://www.football-lab.jp/fctk/")

    def test_generate_match_external_links_structure(self) -> None:
        """Test complete direct external links dict structure."""
        links = generate_match_external_links(self.mw13_match)
        self.assertIn("youtube_highlights", links)
        self.assertIn("jleague_official", links)
        self.assertIn("home_official_review", links)
        self.assertIn("away_official_review", links)
        self.assertIn("yahoo_soccer", links)
        self.assertIn("football_lab", links)

        # Check direct URLs
        self.assertEqual(
            links["yahoo_soccer"]["url"],
            "https://soccer.yahoo.co.jp/jleague/category/j1/game/2026103109/summary",
        )
        self.assertEqual(
            links["football_lab"]["url"],
            "https://www.football-lab.jp/okay/report/?year=2026&month=10&date=31",
        )
        self.assertEqual(
            links["jleague_official"]["url"],
            "https://www.jleague.jp/match/j1/2026/103109/",
        )


def urllib_unquote(url: str) -> str:
    """Helper to unquote URL for testing assertions."""
    import urllib.parse
    return urllib.parse.unquote_plus(url)


if __name__ == "__main__":
    unittest.main()
