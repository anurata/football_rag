# -*- coding: utf-8 -*-
"""
Tests for Match Report Card View Component and Critique Generation.
(tests/test_match_report_card_view.py)
"""

import unittest
from views.components.match.report_card_section import (
    load_match_report_cards,
    _get_rank_badge_html,
    _RANK_COLORS,
)
from pipeline.match_report_card_calculator import MatchReportCardCalculator


class TestMatchReportCardView(unittest.TestCase):
    """Test suite for match report card component data loading and critique formatting."""

    def setUp(self) -> None:
        self.calc = MatchReportCardCalculator()
        self.match_id = "20261025_FCT_MIT"
        self.home_id = "FCT"
        self.away_id = "MIT"

    def test_load_match_report_cards(self) -> None:
        """Verify load_match_report_cards loads valid data for both clubs."""
        data = load_match_report_cards(
            match_id=self.match_id,
            home_id=self.home_id,
            away_id=self.away_id,
        )
        self.assertIn("home", data)
        self.assertIn("away", data)

        home = data["home"]
        away = data["away"]

        # Check required fields
        for card in [home, away]:
            self.assertIn("rank", card)
            self.assertIn("total_score", card)
            self.assertIn("metrics", card)
            self.assertIn("critique", card)

            # Check critique fields
            critique = card["critique"]
            self.assertIn("headline", critique)
            self.assertIn("text", critique)
            self.assertTrue(len(critique["headline"]) > 0)
            self.assertTrue(len(critique["text"]) > 0)

            # Check 6 metrics
            metrics = card["metrics"]
            self.assertEqual(len(metrics), 6)
            for m_key in [
                "game_dominance",
                "individual_power",
                "style_execution",
                "duels_intensity",
                "team_cohesion",
                "excitement_index",
            ]:
                self.assertIn(m_key, metrics)
                self.assertIsInstance(metrics[m_key]["score"], int)
                self.assertTrue(0 <= metrics[m_key]["score"] <= 10)

    def test_rank_badge_html(self) -> None:
        """Verify rank badge HTML formatting."""
        for rank, color in _RANK_COLORS.items():
            badge = _get_rank_badge_html(rank)
            self.assertIn(f"background-color: {color}", badge)
            self.assertIn(f"{rank} ランク", badge)

    def test_generate_critique_branches(self) -> None:
        """Verify critique text contains appropriate tone for high vs low scores."""
        dummy_high = {
            "rank": "S",
            "total_score": 55,
            "score": "3-0",
            "is_home": True,
            "metrics": {
                "game_dominance": {"name": "①ゲーム支配", "score": 9, "details": {}},
                "individual_power": {"name": "②個人パワー", "score": 9, "details": {}},
                "style_execution": {"name": "③スタイル発揮", "score": 10, "details": {}},
                "duels_intensity": {"name": "④球際", "score": 9, "details": {}},
                "team_cohesion": {"name": "⑤リレーション", "score": 9, "details": {}},
                "excitement_index": {
                    "name": "⑥興奮度",
                    "score": 9,
                    "details": {"reasons": ["伝統のダービーマッチでの勝利 (+1.5)"]},
                },
            },
        }
        critique_high = self.calc.generate_critique(dummy_high)
        self.assertIn("最高評価", critique_high["headline"])
        self.assertIn("白星", critique_high["text"])
        self.assertIn("本拠地", critique_high["text"])

        dummy_low = {
            "rank": "D",
            "total_score": 10,
            "score": "0-3",
            "is_home": False,
            "metrics": {
                "game_dominance": {"name": "①ゲーム支配", "score": 2, "details": {}},
                "individual_power": {"name": "②個人パワー", "score": 2, "details": {}},
                "style_execution": {"name": "③スタイル発揮", "score": 1, "details": {}},
                "duels_intensity": {"name": "④球際", "score": 2, "details": {}},
                "team_cohesion": {"name": "⑤リレーション", "score": 2, "details": {}},
                "excitement_index": {"name": "⑥興奮度", "score": 1, "details": {}},
            },
        }
        critique_low = self.calc.generate_critique(dummy_low)
        self.assertIn("完敗", critique_low["headline"])
        self.assertIn("敗戦", critique_low["text"])
        self.assertIn("アウェイ", critique_low["text"])


if __name__ == "__main__":
    unittest.main()
