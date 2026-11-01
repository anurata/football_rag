# -*- coding: utf-8 -*-
"""
Unit tests for DeterministicTacticalEnricher (tests/test_match_tactical_enricher.py).
Strictly verifies elimination of Outcome Bias and conformance with
TACTICAL_PHILOSOPHY_AND_MANIFESTO.md.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.match_tactical_enricher import DeterministicTacticalEnricher


class TestDeterministicTacticalEnricher(unittest.TestCase):
    """Test suite for DeterministicTacticalEnricher."""

    def setUp(self) -> None:
        self.enricher = DeterministicTacticalEnricher(db_path=Path("data/football.db"))

    def test_calculate_deep_metrics(self) -> None:
        flab_h = {
            "m30_entries": 35,
            "pa_entries": 10,
            "distance_m": 115000,
            "sprints": 150,
        }
        flab_a = {
            "m30_entries": 25,
            "pa_entries": 5,
            "distance_m": 112000,
            "sprints": 130,
        }
        metrics = self.enricher._calculate_deep_metrics(
            flab_h=flab_h,
            flab_a=flab_a,
            h_score=2,
            a_score=1,
        )
        self.assertEqual(metrics["field_tilt"]["home_field_tilt"], 58.3)
        self.assertEqual(metrics["conversion_rates"]["home"]["rate_30_to_pa"], 28.6)

    def test_synthesize_tactical_highlights_grounded(self) -> None:
        flab_h = {
            "shots": 14,
            "shots_on_target": 6,
            "possession_rate": 58.0,
            "passes": 520,
            "crosses": 12,
            "m30_entries": 42,
            "pa_entries": 12,
            "distance_m": 118000,
            "sprints": 160,
        }
        flab_a = {
            "shots": 8,
            "shots_on_target": 2,
            "possession_rate": 42.0,
            "passes": 310,
            "crosses": 8,
            "m30_entries": 18,
            "pa_entries": 3,
            "distance_m": 114000,
            "sprints": 130,
        }
        deep_metrics = self.enricher._calculate_deep_metrics(
            flab_h=flab_h,
            flab_a=flab_a,
            h_score=3,
            a_score=0,
        )
        events = [
            {
                "minute": 23,
                "player_name": "仲川 輝人",
                "event_type": "GOAL",
                "description_text": "右足ミドルで先制ゴールを決める",
            },
        ]
        formations = {
            "home_initial": "4-4-2",
            "away_initial": "4-4-2",
        }
        highlights = self.enricher._synthesize_tactical_highlights(
            h_id="FCT",
            a_id="MIT",
            h_name="FC東京",
            a_name="水戸ホーリーホック",
            h_score=3,
            a_score=0,
            formations=formations,
            flab_h=flab_h,
            flab_a=flab_a,
            deep_metrics=deep_metrics,
            events=events,
        )
        self.assertGreaterEqual(len(highlights), 3)
        joined = " ".join(highlights)

        # 1. Base style & intent
        self.assertIn("【基本スタイルと今節の狙い】", joined)
        self.assertIn("FC東京", joined)
        self.assertIn("水戸ホーリーホック", joined)

        # 2. Dynamic Clash
        self.assertIn("【せめぎ合いの力学と内容評価】", joined)

        # 3. Content vs Result Discrepancy (Elimination of outcome bias)
        self.assertIn("【内容と結果の因果・構造的総括】", joined)
        self.assertIn("内容と結果の一致", joined)

    def test_outcome_bias_elimination_tactical_superiority_vs_loss(self) -> None:
        """Verify that a team dominating territory but losing on counter gets proper grounded explanation."""
        flab_h = {
            "shots": 18,
            "shots_on_target": 7,
            "possession_rate": 65.0,
            "m30_entries": 50,
            "pa_entries": 15,
            "distance_m": 115000,
            "sprints": 150,
        }
        flab_a = {
            "shots": 3,
            "shots_on_target": 1,
            "possession_rate": 35.0,
            "m30_entries": 10,
            "pa_entries": 2,
            "distance_m": 112000,
            "sprints": 120,
        }
        deep_metrics = self.enricher._calculate_deep_metrics(
            flab_h=flab_h,
            flab_a=flab_a,
            h_score=0,
            a_score=1,
        )
        events = [
            {
                "minute": 85,
                "player_name": "相手FW",
                "event_type": "GOAL",
                "description_text": "ロングカウンターから先制ゴールを決める",
            },
        ]
        formations = {
            "home_initial": "4-2-3-1",
            "away_initial": "5-4-1",
        }
        highlights = self.enricher._synthesize_tactical_highlights(
            h_id="KAW",
            a_id="OKA",
            h_name="川崎フロンターレ",
            a_name="ファジアーノ岡山",
            h_score=0,
            a_score=1,
            formations=formations,
            flab_h=flab_h,
            flab_a=flab_a,
            deep_metrics=deep_metrics,
            events=events,
        )
        joined = " ".join(highlights)
        self.assertIn("内容と結果の乖離", joined)
        self.assertIn("試合をデザインし狙い通りにピッチを支配したのは川崎フロンターレ", joined)
        self.assertIn("ワンチャンスの決定打", joined)


if __name__ == "__main__":
    unittest.main()
