"""
Unit Tests for Match Context Calculator (tests/test_match_context.py).

Tests deterministic calculation of:
- Schedule, Rest Days, Fatigue Risk, and Consecutive Away Matches
- Disciplinary Status (Suspensions from previous match red cards & Warning Reaches)
- Weather & Pitch Conditions (Extreme heat, Rain, Slippery turf)
- Loan Player Restrictions (契約条項対戦不可)
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.calculate_match_context import MatchContextCalculator


class TestMatchContextCalculator(unittest.TestCase):
    """Test suite for deterministic MatchContextCalculator."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.calculator = MatchContextCalculator()

    def test_stadium_and_loan_masters_loaded(self) -> None:
        """Verify master JSON files are properly loaded without syntax errors."""
        self.assertGreater(len(self.calculator.stadium_master), 0)
        self.assertIn("味の素スタジアム", self.calculator.stadium_master)
        self.assertIn("PEACE STADIUM Connected by SoftBank", self.calculator.stadium_master)
        self.assertGreater(len(self.calculator.loan_master), 0)

    def test_schedule_fatigue_congested_and_away(self) -> None:
        """
        Test MW5 (2026-09-02 vs Shimizu S-Pulse):
        - Previous match was MW4 (2026-08-29 vs Nagasaki)
        - Days between: 4 days -> Rest days: 中3日
        - Consecutive away: True (Nagasaki Away -> Shimizu Away)
        - Fatigue risk: HIGH or EXTREME
        """
        res = self.calculator.calculate_schedule_fatigue(
            team_id="FCT",
            current_date_str="2026-09-02",
            current_stadium="ＩＡＩスタジアム日本平",
            is_home=False,
        )
        self.assertEqual(res["rest_days"], 3)
        self.assertTrue(res["is_congested"])
        self.assertTrue(res["is_consecutive_away"])
        self.assertEqual(res["travel_distance_km"], 170)
        self.assertIn(res["fatigue_risk_level"], ["HIGH", "EXTREME"])

    def test_disciplinary_red_card_suspension_mw2(self) -> None:
        """
        Test MW2 (2026-08-15 vs Vissel Kobe):
        - In MW1 (2026-08-08), Kento Hashimoto received a red card (直前節一発退場)
        - In MW2, Kento Hashimoto MUST be flagged as suspended.
        """
        res = self.calculator.calculate_disciplinary_status(
            team_id="FCT",
            current_date_str="2026-08-15",
        )
        suspended_names = [p["player_name"] for p in res["suspended_players"]]
        self.assertTrue(
            any("橋本" in name for name in suspended_names),
            f"Kento Hashimoto should be suspended for MW2, got: {suspended_names}",
        )

    def test_disciplinary_red_card_suspension_mw9(self) -> None:
        """
        Test MW9 (2026-10-10 vs Urawa Reds):
        - In MW8 (2026-09-19 vs Nagoya), Takahiro Ko received a red card (警告2枚)
        - In MW9, Takahiro Ko MUST be flagged as suspended.
        """
        res = self.calculator.calculate_disciplinary_status(
            team_id="FCT",
            current_date_str="2026-10-10",
        )
        suspended_names = [p["player_name"] for p in res["suspended_players"]]
        self.assertTrue(
            any("高" in name and "宇洋" in name for name in suspended_names),
            f"Takahiro Ko should be suspended for MW9, got: {suspended_names}",
        )

    def test_disciplinary_warning_reach_mw12(self) -> None:
        """
        Test MW12 (2026-10-25 vs Mito Hollyhock):
        - Kein Sato accumulated yellows in MW1 and MW8 (2 yellows before MW12).
        - Checks cumulative tracking accuracy.
        """
        res = self.calculator.calculate_disciplinary_status(
            team_id="FCT",
            current_date_str="2026-10-25",
        )
        self.assertIn("all_cumulative_yellows", res)
        yellows = res["all_cumulative_yellows"]
        sato_count = next((v for k, v in yellows.items() if "佐藤" in k and "恵允" in k), 0)
        self.assertGreaterEqual(
            sato_count,
            2,
            f"Kein Sato should have at least 2 yellows prior to MW12, got {sato_count}",
        )

    def test_weather_pitch_extreme_heat(self) -> None:
        """
        Test MW1 (20260808_FCT_ZEL):
        - Weather: 晴 / 気温: 29.7℃ / 湿度: 76%
        - Should be marked as is_extreme_heat=True and cooling_break_required=True
        """
        res = self.calculator.calculate_weather_pitch_context(
            match_id="20260808_FCT_ZEL",
        )
        self.assertTrue(res["is_extreme_heat"])
        self.assertTrue(res["cooling_break_required"])
        self.assertEqual(res["temperature_c"], 29.7)
        self.assertEqual(res["humidity_percent"], 76)
        self.assertIn("酷暑", res["tactical_implications"])

    def test_weather_pitch_rain_slippery(self) -> None:
        """
        Test MW3 (20260821_FCT_JEF):
        - Weather: のち雨 / 気温: 27.9℃ / 湿度: 89%
        - Should be marked as is_rain_slippery=True
        """
        res = self.calculator.calculate_weather_pitch_context(
            match_id="20260821_FCT_JEF",
        )
        self.assertTrue(res["is_rain_slippery"])
        self.assertIn("雨", res["weather_condition"])
        self.assertIn("スリッピー", res["tactical_implications"])

    def test_loan_restrictions_clause(self) -> None:
        """
        Test Loan Player Restriction Clauses:
        - Against Kashima Antlers (KAS): Ryotaro Araki is restricted.
        - Against Albirex Niigata (ALB): Shion Homma is restricted.
        - Against Machida Zelvia (ZEL): No restriction.
        """
        res_kas = self.calculator.check_loan_restrictions(
            current_team_id="FCT",
            opponent_team_id="KAS",
        )
        self.assertTrue(res_kas["has_loan_restriction"])
        self.assertTrue(any("荒木" in p["player_name"] for p in res_kas["restricted_players"]))

        res_zel = self.calculator.check_loan_restrictions(
            current_team_id="FCT",
            opponent_team_id="ZEL",
        )
        self.assertFalse(res_zel["has_loan_restriction"])
        self.assertEqual(len(res_zel["restricted_players"]), 0)

    def test_injury_condition_context_mw12(self) -> None:
        """
        Test Injury & Condition extraction in MW12 (20261025_FCT_MIT):
        - Should extract active injuries (Henrique Trevisan, Nakagawa limited minutes, etc.)
        - Should extract coach mentions ('連戦かつ怪我人も多い状況で') from markdown
        """
        res = self.calculator.get_injury_condition_context(
            team_id="FCT",
            current_date_str="2026-10-25",
            match_id="20261025_FCT_MIT",
        )
        self.assertGreater(len(res["active_injuries"]), 0)
        self.assertIn("仲川 輝人", [p["player_name"] for p in res["active_injuries"]])
        self.assertGreater(len(res["coach_mentions"]), 0)
        self.assertTrue(any("怪我人" in m for m in res["coach_mentions"]))

    def test_get_full_match_context(self) -> None:
        """Verify full integration returns all 5 context components."""
        full = self.calculator.get_full_match_context(
            team_id="FCT",
            opponent_team_id="MIT",
            match_id="20261025_FCT_MIT",
            date_str="2026-10-25",
            stadium="味の素スタジアム",
            is_home=True,
        )
        self.assertEqual(full["match_id"], "20261025_FCT_MIT")
        self.assertIn("schedule_fatigue", full)
        self.assertIn("disciplinary", full)
        self.assertIn("weather_pitch", full)
        self.assertIn("loan_restrictions", full)
        self.assertIn("injury_condition", full)


if __name__ == "__main__":
    unittest.main()

