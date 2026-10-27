"""
Unit tests for Deep Tactical Metrics Calculator (tests/test_deep_metrics.py).

Validates calculation of:
- 30m -> PA & PA -> Shot conversion rates
- Field Tilt (Attacking 3rd share %)
- CBP rankings and bench impact
- Yahoo timeline event aggregation
"""

import unittest
from pathlib import Path
from scripts.calculate_deep_metrics import (
    calculate_match_deep_metrics,
    calculate_conversion_rates,
    calculate_field_tilt,
    calculate_cbp_rankings,
    aggregate_timeline_events,
)


class TestDeepMetrics(unittest.TestCase):
    """深層戦術指標算出ロジックの単体テスト."""

    def setUp(self) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
        self.sample_match_id = "2026102505"  # 水戸戦（成功事例）

    def test_calculate_conversion_rates_synthetic(self) -> None:
        """進入変換率の数式・評価判定テスト."""
        synthetic_players = [
            {
                "HV": "1",
                "M30PlayCount": "100",
                "PAPlayCount": "40",
                "Shoot": "20",
            },
            {
                "HV": "2",
                "M30PlayCount": "50",
                "PAPlayCount": "10",
                "Shoot": "2",
            },
        ]
        res = calculate_conversion_rates(synthetic_players)
        home = res["home"]
        away = res["away"]

        # Home: 40/100 = 40.0%, 20/40 = 50.0%
        self.assertEqual(home["rate_30_to_pa"], 40.0)
        self.assertEqual(home["rate_pa_to_shot"], 50.0)
        self.assertIn("高効率侵入", home["eval_30_to_pa"])
        self.assertIn("高脅威フィニッシュ", home["eval_pa_to_shot"])

        # Away: 10/50 = 20.0%, 2/10 = 20.0%
        self.assertEqual(away["rate_30_to_pa"], 20.0)
        self.assertEqual(away["rate_pa_to_shot"], 20.0)
        self.assertIn("外周停滞", away["eval_30_to_pa"])
        self.assertIn("決定力欠如", away["eval_pa_to_shot"])

    def test_calculate_field_tilt_synthetic(self) -> None:
        """敵陣支配度（Field Tilt）の算出テスト."""
        synthetic_players = [
            {"HV": "1", "At3rdPlayCount": "150"},
            {"HV": "2", "At3rdPlayCount": "50"},
        ]
        res = calculate_field_tilt(synthetic_players)
        # Total: 200, Home: 75.0%, Away: 25.0%
        self.assertEqual(res["home_field_tilt"], 75.0)
        self.assertEqual(res["away_field_tilt"], 25.0)
        self.assertIn("敵陣圧倒", res["home_eval"])
        self.assertIn("自陣防戦", res["away_eval"])

    def test_calculate_cbp_rankings_synthetic(self) -> None:
        """CBPランキング抽出テスト."""
        matrix = [
            {"player_name": "選手A", "team_side": "HOME", "attack": "4.5", "defense": "1.0", "gain": "3.0", "pass": "5.0", "shoot": "2.0"},
            {"player_name": "選手B", "team_side": "HOME", "attack": "2.1", "defense": "4.0", "gain": "8.0", "pass": "3.0", "shoot": "0.5"},
            {"player_name": "選手C", "team_side": "AWAY", "attack": "3.0", "defense": "2.0", "gain": "5.0", "pass": "4.0", "shoot": "1.0"},
        ]
        res = calculate_cbp_rankings(matrix)
        home = res["home"]
        self.assertEqual(home["top_attack"][0]["name"], "選手A")
        self.assertEqual(home["top_defense"][0]["name"], "選手B")
        self.assertEqual(home["top_gain"][0]["name"], "選手B")

    def test_aggregate_timeline_events_synthetic(self) -> None:
        """速報イベント集計テスト."""
        timeline = [
            {"time": "前 32分", "text": "仲川がヘディングでゴールを決める", "team": "FC東京", "is_goal": True, "is_card": False, "is_substitution": False},
            {"time": "後 10分", "text": "ファウルでイエローカード提示", "team": "水戸", "is_goal": False, "is_card": True, "is_substitution": False},
            {"time": "後 20分", "text": "選手交代：山田に代わってマルセロヒアン", "team": "FC東京", "is_goal": False, "is_card": False, "is_substitution": True},
        ]
        res = aggregate_timeline_events(timeline, home_team_name="FC東京")
        self.assertEqual(res["total_events"], 3)
        self.assertEqual(res["home_counts"]["goals"], 1)
        self.assertEqual(res["away_counts"]["yellow_cards"], 1)
        self.assertEqual(res["home_counts"]["subs"], 1)

    def test_calculate_real_match_deep_metrics(self) -> None:
        """水戸戦の実生データを用いた完全統合テスト."""
        res = calculate_match_deep_metrics(self.sample_match_id, base_dir=self.base_dir)
        self.assertIn("conversion_rates", res)
        self.assertIn("field_tilt", res)
        self.assertIn("cbp_rankings", res)
        self.assertIn("timeline_events", res)

        # 実生データの検証
        conv = res["conversion_rates"]
        self.assertGreater(conv["home"]["m30_count"], 0)
        self.assertGreater(conv["home"]["pa_count"], 0)

        tilt = res["field_tilt"]
        self.assertGreater(tilt["home_field_tilt"], 0.0)

        events = res["timeline_events"]
        self.assertGreater(events["total_events"], 50)
        self.assertGreaterEqual(events["home_counts"]["goals"], 6)  # 6-0勝利


if __name__ == "__main__":
    unittest.main()
