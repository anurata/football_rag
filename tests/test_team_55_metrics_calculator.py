# -*- coding: utf-8 -*-
"""
Tests for Generalized Team 55 Tactical Metrics Calculator.
(tests/test_team_55_metrics_calculator.py)
"""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from pipeline.db import DEFAULT_DB_PATH
from pipeline.team_55_metrics_calculator import Team55MetricsCalculator


class TestTeam55MetricsCalculator(unittest.TestCase):
    """Test suite for generalized 55 tactical metrics calculation across multiple J1 clubs."""

    def test_calculate_matches_for_zelvia(self) -> None:
        """Verify calculations for Machida Zelvia (ZEL)."""
        calc = Team55MetricsCalculator(team_id="ZEL", db_path=DEFAULT_DB_PATH)
        results = calc.calculate_all_matches()
        self.assertEqual(len(results), 12, "ZEL must have 12 matches calculated")

        first_match = results[0]
        self.assertEqual(first_match["チーム"], "ZEL")
        self.assertIn("31_チーム凸包面積(㎡)", first_match)
        self.assertIn("43_ポアソン期待勝点(xPTS)", first_match)
        self.assertIn("48_BPI(ボール前進総合指数)", first_match)
        self.assertTrue(0.0 <= first_match["43_ポアソン期待勝点(xPTS)"] <= 3.0)

    def test_calculate_matches_for_antlers(self) -> None:
        """Verify calculations for Kashima Antlers (KAS)."""
        calc = Team55MetricsCalculator(team_id="KAS", db_path=DEFAULT_DB_PATH)
        results = calc.calculate_all_matches()
        self.assertEqual(len(results), 12, "KAS must have 12 matches calculated")

        for r in results:
            self.assertEqual(r["チーム"], "KAS")
            self.assertFalse(np.isnan(r["48_BPI(ボール前進総合指数)"]))
            self.assertFalse(np.isinf(r["48_BPI(ボール前進総合指数)"]))


if __name__ == "__main__":
    unittest.main()

