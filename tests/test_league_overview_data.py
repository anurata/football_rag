"""
tests/test_league_overview_data.py

Unit tests for pipeline/league_overview_data.py.
Validates league standings, xPTS, matchweek cards, rankings, and tactical maps.
"""

import os
import sys
import unittest
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH
from pipeline.league_overview_data import (
    get_available_seasons,
    get_league_standings,
    get_league_stats_rankings,
    get_matchweek_matches,
    get_tactical_positioning_map_data,
    get_team_metadata_map,
)


class TestLeagueOverviewData(unittest.TestCase):
    """Test suite for J-League overview data aggregation."""

    @classmethod
    def setUpClass(cls):
        """Verify DB exists before running tests."""
        if not os.path.exists(DEFAULT_DB_PATH):
            raise unittest.SkipTest(f"Database file not found: {DEFAULT_DB_PATH}")

    def test_get_available_seasons(self):
        """Test retrieving available seasons."""
        seasons = get_available_seasons(db_path=DEFAULT_DB_PATH)
        self.assertIsInstance(seasons, list)
        self.assertGreater(len(seasons), 0)
        self.assertIn(2026, seasons)

    def test_get_team_metadata_map(self):
        """Test team metadata mapping."""
        meta = get_team_metadata_map(db_path=DEFAULT_DB_PATH)
        self.assertIsInstance(meta, dict)
        self.assertIn("FCT", meta)
        fct = meta["FCT"]
        self.assertEqual(fct["team_id"], "FCT")
        self.assertIn("name", fct)
        self.assertIn("short_name", fct)

    def test_get_league_standings(self):
        """Test league standings and xPTS calculation."""
        standings = get_league_standings(season=2026, db_path=DEFAULT_DB_PATH)
        self.assertIsInstance(standings, list)
        self.assertGreater(len(standings), 0)

        # Check fields of top team
        top_team = standings[0]
        self.assertEqual(top_team["rank"], 1)
        self.assertIn("points", top_team)
        self.assertIn("played", top_team)
        self.assertIn("gf", top_team)
        self.assertIn("ga", top_team)
        self.assertIn("gd", top_team)
        self.assertIn("xpts_total", top_team)
        self.assertIn("luck_index", top_team)
        self.assertIn("form", top_team)
        self.assertIn("xpts_rank", top_team)

        # Mathematical consistency
        for team in standings:
            self.assertEqual(team["gd"], team["gf"] - team["ga"])
            expected_luck = round(team["points"] - team["xpts_total"], 2)
            self.assertAlmostEqual(team["luck_index"], expected_luck, delta=0.05)
            self.assertLessEqual(len(team["form"]), 5)

        # Standings sorted descending by points
        for i in range(len(standings) - 1):
            t1 = standings[i]
            t2 = standings[i + 1]
            self.assertGreaterEqual(
                (t1["points"], t1["gd"], t1["gf"]),
                (t2["points"], t2["gd"], t2["gf"]),
            )

    def test_get_matchweek_matches(self):
        """Test retrieving matchweek cards."""
        res = get_matchweek_matches(season=2026, db_path=DEFAULT_DB_PATH)
        self.assertIsInstance(res, dict)
        self.assertIn("available_matchweeks", res)
        self.assertIn("selected_matchweek", res)
        self.assertIn("matches", res)
        self.assertGreater(len(res["available_matchweeks"]), 0)
        self.assertGreater(len(res["matches"]), 0)

        first_match = res["matches"][0]
        self.assertIn("match_id", first_match)
        self.assertIn("home_team_id", first_match)
        self.assertIn("away_team_id", first_match)
        self.assertIn("home_team_name", first_match)
        self.assertIn("away_team_name", first_match)
        self.assertIn("youtube_url", first_match)
        self.assertIn("official_report_url", first_match)

    def test_get_league_stats_rankings(self):
        """Test team and player leaderboards."""
        rankings = get_league_stats_rankings(season=2026, db_path=DEFAULT_DB_PATH, top_n=5)
        self.assertIsInstance(rankings, dict)
        self.assertIn("team_rankings", rankings)
        self.assertIn("player_rankings", rankings)

        # Team rankings
        team_rk = rankings["team_rankings"]
        for cat in ["possession", "chance_create", "distance", "sprints"]:
            self.assertIn(cat, team_rk)
            items = team_rk[cat]
            self.assertLessEqual(len(items), 5)
            if items:
                self.assertEqual(items[0]["rank"], 1)
                self.assertIn("team_name", items[0])
                self.assertIn("value", items[0])

        # Player rankings
        player_rk = rankings["player_rankings"]
        for pcat in ["goals", "assists", "cbp_total", "sprints"]:
            self.assertIn(pcat, player_rk)
            p_items = player_rk[pcat]
            self.assertLessEqual(len(p_items), 5)
            if p_items:
                self.assertEqual(p_items[0]["rank"], 1)
                self.assertIn("player_name", p_items[0])
                self.assertIn("team_name", p_items[0])
                self.assertIn("value", p_items[0])

    def test_get_tactical_positioning_map_data(self):
        """Test 4-quadrant positioning map data."""
        presets = ["possession_vs_press", "xg_attack_vs_defense", "physical_distance_vs_sprints"]
        for preset in presets:
            data = get_tactical_positioning_map_data(season=2026, metric_preset=preset, db_path=DEFAULT_DB_PATH)
            self.assertIsInstance(data, dict)
            self.assertEqual(data["preset"], preset)
            self.assertIn("x_avg", data)
            self.assertIn("y_avg", data)
            self.assertIn("quadrant_labels", data)
            self.assertIn("teams", data)
            self.assertGreater(len(data["teams"]), 0)

            team0 = data["teams"][0]
            self.assertIn("team_id", team0)
            self.assertIn("x", team0)
            self.assertIn("y", team0)


if __name__ == "__main__":
    unittest.main()
