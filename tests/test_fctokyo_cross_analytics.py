# -*- coding: utf-8 -*-
"""
Tests for FC Tokyo Cross-Analytics Engine (tests/test_fctokyo_cross_analytics.py).
Verifies 15-minute segments, unit synergies, and opponent clustering.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.db import DEFAULT_DB_PATH
from pipeline.fctokyo_cross_analytics import FCTokyoCrossAnalyticsEngine


class TestFCTokyoCrossAnalytics(unittest.TestCase):
    """Test suite for Cross Analytics Engine."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.output_json = self.temp_dir / "test_synthesis.json"
        self.engine = FCTokyoCrossAnalyticsEngine(db_path=DEFAULT_DB_PATH)

    def tearDown(self) -> None:
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_run_and_persist_synthesis(self) -> None:
        """Verify full cross-analytics execution and JSON persistence."""
        data = self.engine.run_and_persist_synthesis(output_path=self.output_json)
        self.assertTrue(self.output_json.exists(), "JSON output must exist")

        # 1. Verify 15-minute dynamics
        time_segs = data.get("time_segment_dynamics", {})
        expected_segs = ["0-15", "16-30", "31-45+", "46-60", "61-75", "76-90+"]
        for seg in expected_segs:
            self.assertIn(seg, time_segs)
            self.assertIn("fct_goals", time_segs[seg])
            self.assertIn("opp_goals", time_segs[seg])
            self.assertGreaterEqual(time_segs[seg]["fct_goals"], 0)

        # 2. Verify unit synergy
        synergy = data.get("starter_unit_synergy", {})
        self.assertIn("center_back_units", synergy)
        self.assertIn("central_midfield_units", synergy)
        self.assertGreater(len(synergy["center_back_units"]), 0)

        # 3. Verify opponent archetype clustering
        opp_matrix = data.get("opponent_archetype_resistance", {})
        total_classified_matches = sum(v["match_count"] for v in opp_matrix.values())
        self.assertEqual(total_classified_matches, 12, "All 12 matches must be classified into archetypes")

        for arch, stats in opp_matrix.items():
            self.assertIn("win_rate_pct", stats)
            self.assertIn("avg_conv_30_to_pa_pct", stats)
            self.assertTrue(0.0 <= stats["win_rate_pct"] <= 100.0)


if __name__ == "__main__":
    unittest.main()

