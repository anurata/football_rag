"""Unit tests for scripts/validate_xg_xa_metrics.py."""

from __future__ import annotations

import unittest
import pandas as pd
from scripts.validate_xg_xa_metrics import (
    calculate_statistical_correlations,
    calculate_positional_averages,
    get_top_performers,
)


class TestValidateXgXaMetrics(unittest.TestCase):
    """Test suite for metrics validation functions."""

    def setUp(self) -> None:
        self.mock_df = pd.DataFrame([
            {
                "player_name": "FW選手A",
                "team_id": "FCT",
                "position": "FW",
                "total_minutes": 900,
                "total_goals": 8,
                "total_assists": 2,
                "total_xg": 7.5,
                "total_xa": 1.8,
                "xg90": 0.75,
                "xa90": 0.18,
                "goals90": 0.80,
                "assists90": 0.20,
            },
            {
                "player_name": "MF選手B",
                "team_id": "FCT",
                "position": "MF",
                "total_minutes": 900,
                "total_goals": 2,
                "total_assists": 6,
                "total_xg": 2.2,
                "total_xa": 5.4,
                "xg90": 0.22,
                "xa90": 0.54,
                "goals90": 0.20,
                "assists90": 0.60,
            },
            {
                "player_name": "DF選手C",
                "team_id": "FCT",
                "position": "DF",
                "total_minutes": 900,
                "total_goals": 1,
                "total_assists": 1,
                "total_xg": 0.8,
                "total_xa": 0.9,
                "xg90": 0.08,
                "xa90": 0.09,
                "goals90": 0.10,
                "assists90": 0.10,
            },
            {
                "player_name": "GK選手D",
                "team_id": "FCT",
                "position": "GK",
                "total_minutes": 900,
                "total_goals": 0,
                "total_assists": 0,
                "total_xg": 0.0,
                "total_xa": 0.0,
                "xg90": 0.0,
                "xa90": 0.0,
                "goals90": 0.0,
                "assists90": 0.0,
            },
        ])

    def test_calculate_statistical_correlations(self) -> None:
        """Verify correlation computations."""
        corrs = calculate_statistical_correlations(self.mock_df)
        self.assertIn("pearson_goals_xg", corrs)
        self.assertIn("pearson_assists_xa", corrs)
        self.assertGreater(corrs["pearson_goals_xg"], 0.90)
        self.assertGreater(corrs["pearson_assists_xa"], 0.90)

    def test_calculate_positional_averages(self) -> None:
        """Verify positional averages reflect positional hierarchy."""
        pos = calculate_positional_averages(self.mock_df)
        self.assertIn("FW", pos)
        self.assertIn("MF", pos)
        self.assertIn("DF", pos)
        self.assertIn("GK", pos)

        # FW xG > MF xG > DF xG > GK xG
        self.assertGreater(pos["FW"]["avg_xg90"], pos["MF"]["avg_xg90"])
        self.assertGreater(pos["MF"]["avg_xg90"], pos["DF"]["avg_xg90"])
        self.assertGreaterEqual(pos["DF"]["avg_xg90"], pos["GK"]["avg_xg90"])

    def test_get_top_performers(self) -> None:
        """Verify leaderboard extraction."""
        tops = get_top_performers(self.mock_df, top_n=2)
        self.assertEqual(len(tops["top_xg"]), 2)
        self.assertEqual(tops["top_xg"][0]["name"], "FW選手A")
        self.assertEqual(tops["top_xa"][0]["name"], "MF選手B")


if __name__ == "__main__":
    unittest.main()

