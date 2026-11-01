# -*- coding: utf-8 -*-
"""
Tests for Generalized Team Cross-Analytics Engine.
(tests/test_team_cross_analytics.py)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.db import DEFAULT_DB_PATH
from pipeline.team_cross_analytics import TeamCrossAnalyticsEngine


class TestTeamCrossAnalyticsEngine(unittest.TestCase):
    """Test suite for multi-club cross-analytics."""

    def test_cross_analytics_for_kashima(self) -> None:
        """Verify cross-analytics engine for Kashima Antlers (KAS)."""
        engine = TeamCrossAnalyticsEngine(team_id="KAS", db_path=DEFAULT_DB_PATH)

        with tempfile.TemporaryDirectory() as tmpdir:
            test_output = Path(tmpdir) / "kas_synthesis.json"
            data = engine.run_and_persist_synthesis(output_path=test_output)

            # 1. Meta checks
            self.assertEqual(data["meta"]["team_id"], "KAS")
            self.assertEqual(data["meta"]["analyzed_matches"], 12)

            # 2. Time segment dynamics checks
            segments = data["time_segment_dynamics"]
            self.assertEqual(len(segments), 6)
            self.assertIn("0-15", segments)
            self.assertIn("team_goals", segments["0-15"])

            # 3. Starter unit synergy checks
            synergy = data["starter_unit_synergy"]
            self.assertIn("center_back_units", synergy)
            self.assertIn("central_midfield_units", synergy)

            # 4. Opponent archetype resistance checks
            arch = data["opponent_archetype_resistance"]
            self.assertTrue(len(arch) > 0, "Must classify opponents into archetypes")
            for a_code, a_val in arch.items():
                self.assertIn(a_code, ["HIGH_PRESS", "MID_BLOCK", "LOW_BLOCK"])
                self.assertIn("win_rate_pct", a_val)


if __name__ == "__main__":
    unittest.main()

