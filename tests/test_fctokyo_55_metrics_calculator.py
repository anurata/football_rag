# -*- coding: utf-8 -*-
"""
Tests for FC Tokyo 55 Tactical Metrics Calculator.
(tests/test_fctokyo_55_metrics_calculator.py)
"""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from pipeline.db import DEFAULT_DB_PATH
from pipeline.fctokyo_55_metrics_calculator import (
    FCTokyo55MetricsCalculator,
    compute_convex_hull_area,
    compute_gini_coefficient,
    compute_poisson_probability,
    compute_shannon_entropy,
    simulate_poisson_match,
)


class TestFCTokyo55MetricsCalculator(unittest.TestCase):
    """Test suite for 55 tactical metrics calculation."""

    def setUp(self) -> None:
        self.calc = FCTokyo55MetricsCalculator(db_path=DEFAULT_DB_PATH)

    def test_convex_hull_and_geometry(self) -> None:
        """Verify Monotone Chain Convex Hull algorithm."""
        # Square: (0,0), (10,0), (10,10), (0,10) -> Area should be 100
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (5.0, 5.0)]
        area = compute_convex_hull_area(square)
        self.assertAlmostEqual(area, 100.0, places=2)

    def test_information_theory_metrics(self) -> None:
        """Verify Shannon entropy and Gini coefficient bounds."""
        equal_touches = [10.0, 10.0, 10.0, 10.0]
        self.assertAlmostEqual(compute_shannon_entropy(equal_touches), 1.0, places=2)
        self.assertAlmostEqual(compute_gini_coefficient(equal_touches), 0.0, places=2)

        skewed_touches = [100.0, 1.0, 1.0, 1.0]
        self.assertLess(compute_shannon_entropy(skewed_touches), 0.6)
        self.assertGreater(compute_gini_coefficient(skewed_touches), 0.6)

    def test_poisson_simulation_bounds(self) -> None:
        """Verify Dixon & Coles Poisson match simulation bounds."""
        pw, pd, pl = simulate_poisson_match(1.5, 1.0)
        self.assertAlmostEqual(pw + pd + pl, 1.0, places=3)
        self.assertGreater(pw, pl, "Higher xG team must have higher win probability")

    def test_calculate_all_matches_validity(self) -> None:
        """Verify full calculation of 55 metrics across all 12 matches."""
        results = self.calc.calculate_all_matches()
        self.assertEqual(len(results), 12, "Must calculate exactly 12 matches for MW1-12")

        for r in results:
            m_id = r["試合ID"]
            # 1. Geometry checks
            self.assertGreater(r["31_チーム凸包面積(㎡)"], 500.0, f"{m_id}: Hull area must be realistic")
            self.assertGreater(r["32_伸縮指数(Stretch Index)"], 5.0, f"{m_id}: Stretch index must be realistic")

            # 2. Entropy and Gini
            self.assertTrue(0.0 <= r["35_タッチ関与シャノンエントロピー"] <= 1.0)
            self.assertTrue(0.0 <= r["36_ビルドアップ集中度ジニ係数"] <= 1.0)

            # 3. Poisson xPTS and Pythagorean
            self.assertTrue(0.0 <= r["43_ポアソン期待勝点(xPTS)"] <= 3.0)
            self.assertTrue(0.0 <= r["44_ピタゴラス期待勝率(%)"] <= 100.0)

            # 4. No NaNs or infinities in numerical fields
            for k, v in r.items():
                if isinstance(v, (int, float)):
                    self.assertFalse(np.isnan(v), f"{m_id} {k} must not be NaN")
                    self.assertFalse(np.isinf(v), f"{m_id} {k} must not be Inf")


if __name__ == "__main__":
    unittest.main()

