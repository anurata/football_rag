"""
tests/test_tactical_matchup_engine.py

Unit and integration tests for TacticalMatchupEngine (pipeline/tactical_matchup_engine.py).
Verifies deterministic extraction of Layer 2 to Layer 6 hypotheses:
- Aerial Duel Mismatch
- In-Behind vs High Line Mismatch
- Dominant Foot Funneling
- Formation & System Space Mismatch
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from pipeline.tactical_matchup_engine import TacticalMatchupEngine, DB_PATH, TEAM_PROFILES_PATH


class TestTacticalMatchupEngine(unittest.TestCase):
    """Test suite for TacticalMatchupEngine."""

    def setUp(self) -> None:
        self.engine = TacticalMatchupEngine(
            db_path=DB_PATH,
            team_profiles_path=TEAM_PROFILES_PATH,
        )

    def test_aerial_duel_mismatch_extraction(self) -> None:
        attackers = [
            {
                "player_name": "マルセロ・ヒアン",
                "position": "FW",
                "height_cm": 189,
                "spaia": {"pa_entries": 8},
                "minutes_played": 85,
            },
            {
                "player_name": "仲川 輝人",
                "position": "FW",
                "height_cm": 160,
                "spaia": {"pa_entries": 3},
                "minutes_played": 60,
            },
        ]
        defenders = [
            {
                "player_name": "相手SB",
                "position": "SB",
                "height_cm": 172,
            },
            {
                "player_name": "相手CB",
                "position": "CB",
                "height_cm": 187,
            },
        ]

        mismatches = self.engine.extract_aerial_duel_mismatches(
            attackers=attackers,
            defenders=defenders,
            att_team_id="FCT",
            def_team_id="OPP",
        )

        self.assertTrue(len(mismatches) >= 1)
        m = mismatches[0]
        self.assertEqual(m["category"], "AERIAL_DUEL_MISMATCH")
        self.assertEqual(m["attacker"], "マルセロ・ヒアン")
        self.assertEqual(m["defender"], "相手SB")
        self.assertEqual(m["height_diff_cm"], 17)
        self.assertIn("layer1_facts", m)
        self.assertIn("layer2_heuristics", m)
        self.assertIn("layer3_explanation", m)
        self.assertIn("layer4_hypothesis", m)
        self.assertIn("layer5_narrative", m)
        self.assertIn("layer6_forecasting", m)

    def test_speed_vs_high_line_extraction(self) -> None:
        attackers = [
            {
                "player_name": "快速FW",
                "position": "FW",
                "max_speed_kmh": 34.8,
                "sprints": 25,
            },
        ]
        defenders = [
            {
                "player_name": "重厚CB",
                "position": "CB",
                "max_speed_kmh": 29.5,
            },
        ]

        # Test against high line team (e.g. FCT or MAR)
        mismatches = self.engine.extract_speed_vs_high_line_mismatches(
            attackers=attackers,
            defenders=defenders,
            att_team_id="ATT",
            def_team_id="MAR",
        )

        self.assertTrue(len(mismatches) >= 1)
        m = mismatches[0]
        self.assertEqual(m["category"], "IN_BEHIND_VS_HIGH_LINE")
        self.assertEqual(m["attacker"], "快速FW")
        self.assertEqual(m["layer1_facts"]["max_speed_kmh"], 34.8)
        self.assertEqual(m["layer1_facts"]["speed_difference_kmh"], 5.3)

    def test_dominant_foot_funneling_extraction(self) -> None:
        # Build-up team with only right-footed CBs
        buildup_players = [
            {"player_name": "右CB1", "position": "CB", "dominant_foot": "右足", "is_starter": 1},
            {"player_name": "右CB2", "position": "CB", "dominant_foot": "右足", "is_starter": 1},
        ]

        mismatches = self.engine.extract_dominant_foot_funneling_mismatches(
            buildup_players=buildup_players,
            pressing_team_id="FCT",
            buildup_team_id="OPP",
        )

        self.assertTrue(len(mismatches) >= 1)
        m = mismatches[0]
        self.assertEqual(m["category"], "DOMINANT_FOOT_FUNNELING")
        self.assertEqual(m["vulnerability_type"], "no_left_footed_cb")
        self.assertEqual(m["layer1_facts"]["left_footed_cb_count"], 0)

    def test_formation_space_mismatch_extraction(self) -> None:
        mismatches = self.engine.extract_formation_space_mismatches(
            home_team_id="FCT",
            away_team_id="SAN",
        )
        # Both are 4-back in our profiles, so test with mock 3-back
        mock_profiles = {
            "teams": {
                "TEAM_4": {"base_formation": "4-4-2"},
                "TEAM_3": {"base_formation": "3-4-2-1"},
            },
        }
        engine_mock = TacticalMatchupEngine(
            db_path=DB_PATH,
            team_profiles_path=Path("dummy_not_exist"),
        )
        engine_mock.team_profiles = mock_profiles["teams"]

        m_list = engine_mock.extract_formation_space_mismatches("TEAM_4", "TEAM_3")
        self.assertEqual(len(m_list), 1)
        self.assertEqual(m_list[0]["category"], "FORMATION_SPACE_MISMATCH")

    def test_analyze_real_match_fct_zel(self) -> None:
        """Integration test on actual match 20260808_FCT_ZEL."""
        res = self.engine.analyze_match_mismatches("20260808_FCT_ZEL")
        self.assertEqual(res["match_id"], "20260808_FCT_ZEL")
        self.assertEqual(res["home_team_id"], "FCT")
        self.assertEqual(res["away_team_id"], "ZEL")
        self.assertTrue(res["total_mismatches_found"] > 0)

        categories = {m["category"] for m in res["mismatches"]}
        # Should have detected at least speed or aerial mismatches
        self.assertTrue("IN_BEHIND_VS_HIGH_LINE" in categories or "AERIAL_DUEL_MISMATCH" in categories)


if __name__ == "__main__":
    unittest.main()
