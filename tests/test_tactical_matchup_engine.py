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
        # Should have detected at least speed or aerial or formation mismatches
        self.assertTrue(
            bool(categories & {"IN_BEHIND_VS_HIGH_LINE", "AERIAL_DUEL_MISMATCH", "FORMATION_SPACE_MISMATCH"}),
        )

    def test_left_footed_lsb_does_not_mask_right_footed_cbs(self) -> None:
        """左SBに左利きが先発していても、CB2枚(RCB/LCB)が右利きなら利き足誘導脆弱性を正しく検出する."""
        buildup_players = [
            {
                "player_name": "ショルツ",
                "primary_role": "RCB",
                "primary_role_group": "CB",
                "primary_lane": "CENTER",
                "dominant_foot": "右足",
                "is_starter": 1,
                "role_stints": [{"from_min": 0, "to_min": 90, "role": "RCB", "role_group": "CB", "lane": "CENTER"}],
            },
            {
                "player_name": "森重 真人",
                "primary_role": "LCB",
                "primary_role_group": "CB",
                "primary_lane": "CENTER",
                "dominant_foot": "右足",
                "is_starter": 1,
                "role_stints": [{"from_min": 0, "to_min": 90, "role": "LCB", "role_group": "CB", "lane": "CENTER"}],
            },
            {
                "player_name": "バングーナガンデ 佳史扶",
                "primary_role": "LSB",
                "primary_role_group": "FB",
                "primary_lane": "LEFT",
                "dominant_foot": "左足",
                "is_starter": 1,
                "role_stints": [{"from_min": 0, "to_min": 90, "role": "LSB", "role_group": "FB", "lane": "LEFT"}],
            },
        ]
        mismatches = self.engine.extract_dominant_foot_funneling_mismatches(
            buildup_players=buildup_players,
            pressing_team_id="ZEL",
            buildup_team_id="FCT",
        )
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["layer1_facts"]["left_footed_cb_count"], 0)
        self.assertIn("森重 真人", mismatches[0]["layer1_facts"]["right_footed_lcb"])

    def test_aerial_requires_opposing_lane_and_overlapping_stint(self) -> None:
        """非対面レーン(RWG vs RSB)や出場時間帯が重ならないペアは除外し、対面(RWG vs LSB)のみ抽出する."""
        attackers = [
            {
                "player_name": "長身右WG",
                "primary_role": "RWG",
                "primary_role_group": "WIDE_ATT",
                "primary_lane": "RIGHT",
                "height_cm": 186,
                "fluidity_tags": [],
                "role_stints": [{"from_min": 0, "to_min": 60, "role": "RWG", "role_group": "WIDE_ATT", "lane": "RIGHT"}],
            },
        ]
        defenders = [
            # 非対面レーン(右SB) -> 除外されるべき
            {
                "player_name": "逆サイド小柄RSB",
                "primary_role": "RSB",
                "primary_role_group": "FB",
                "primary_lane": "RIGHT",
                "height_cm": 170,
                "fluidity_tags": [],
                "role_stints": [{"from_min": 0, "to_min": 90, "role": "RSB", "role_group": "FB", "lane": "RIGHT"}],
            },
            # 対面レーン(左SB)だが65分からの途中出場で時間帯重複なし -> 除外されるべき
            {
                "player_name": "後半途中出場LSB",
                "primary_role": "LSB",
                "primary_role_group": "FB",
                "primary_lane": "LEFT",
                "height_cm": 170,
                "fluidity_tags": [],
                "role_stints": [{"from_min": 65, "to_min": 90, "role": "LSB", "role_group": "FB", "lane": "LEFT"}],
            },
            # 対面レーン(左SB)かつ0〜60分で重複 -> これだけ検出されるべき
            {
                "player_name": "先発対面LSB",
                "primary_role": "LSB",
                "primary_role_group": "FB",
                "primary_lane": "LEFT",
                "height_cm": 171,
                "fluidity_tags": [],
                "role_stints": [{"from_min": 0, "to_min": 65, "role": "LSB", "role_group": "FB", "lane": "LEFT"}],
            },
        ]
        mismatches = self.engine.extract_aerial_duel_mismatches(
            attackers=attackers,
            defenders=defenders,
            att_team_id="FCT",
            def_team_id="OPP",
        )
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["defender"], "先発対面LSB")
        self.assertEqual(mismatches[0]["time_window"], "0〜60分")

    def test_analyze_other_j1_match_mar_kas(self) -> None:
        """FC東京以外のJ1試合(20260807_MAR_KAS: 4-2-3-1 vs 4-4-2)でも実ポジションで動作することを検証."""
        res = self.engine.analyze_match_mismatches("20260807_MAR_KAS")
        self.assertEqual(res["home_formation"], "4-2-3-1")
        self.assertEqual(res["away_formation"], "4-4-2")
        self.assertEqual(res["formation_source"], "match_formations_actual")
        self.assertGreater(res["total_mismatches_found"], 0)


if __name__ == "__main__":
    unittest.main()
