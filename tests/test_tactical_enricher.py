"""
Unit tests for AI Tactical Enricher (tests/test_tactical_enricher.py).

Validates:
- Prompt construction with deep metrics and context
- JSON response stripping and parsing
- End-to-end extraction with mock Gemini client
"""

import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock

from pipeline.tactical_enricher import TacticalEnricher
from agent.gemini_client import GeminiTacticalClient


import tempfile


class TestTacticalEnricher(unittest.TestCase):
    """戦術推論パイプラインの単体テスト."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_client = GeminiTacticalClient(mock_mode=True)
        self.enricher = TacticalEnricher(
            gemini_client=self.mock_client,
            structured_dir=Path(self.temp_dir.name),
        )
        self.sample_id = "2026102505"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_clean_json_string(self) -> None:
        """Markdownフェンスの剥離テスト."""
        raw_md = "```json\n{\"match_id\": \"test\", \"phases\": []}\n```"
        cleaned = self.enricher._clean_json_string(raw_md)
        self.assertTrue(cleaned.startswith("{"))
        self.assertTrue(cleaned.endswith("}"))

    def test_build_enrichment_prompt(self) -> None:
        """プロンプト構築と深層指標の埋め込み検証."""
        metrics = {
            "conversion_rates": {
                "home": {"rate_30_to_pa": 45.2, "eval_30_to_pa": "高効率侵入", "rate_pa_to_shot": 50.0, "eval_pa_to_shot": "高脅威フィニッシュ"},
                "away": {"rate_30_to_pa": 20.0, "eval_30_to_pa": "外周停滞", "rate_pa_to_shot": 25.0, "eval_pa_to_shot": "決定力欠如"},
            },
            "field_tilt": {"home_field_tilt": 62.5, "home_eval": "敵陣圧倒", "away_field_tilt": 37.5, "away_eval": "自陣防戦"},
            "cbp_rankings": {
                "home": {"top_attack": [{"name": "仲川 輝人", "value": 4.12}], "bench_impact": 4.5, "bench_eval": "采配大的中"},
                "away": {"top_attack": [{"name": "選手A", "value": 2.1}], "bench_impact": 0.5, "bench_eval": "交代不発"},
            },
            "timeline_events": {
                "total_events": 100,
                "home_counts": {"shots": 23, "corners": 7, "red_cards": 0},
                "away_counts": {"shots": 12, "corners": 3, "red_cards": 0},
                "key_plays_sample": ["前32分 【ゴール】仲川", "後21分 【ゴール】安斎"],
            },
        }
        raw_context = {
            "home_team": "FC東京",
            "away_team": "水戸ホーリーホック",
            "score": "6-0",
            "report_text": "公式戦評ダイジェスト",
            "coach_home": "松橋 力蔵",
            "coach_away": "森 直樹",
        }

        prompt = self.enricher.build_enrichment_prompt(self.sample_id, metrics, raw_context)
        self.assertIn("FC東京 vs 水戸ホーリーホック", prompt)
        self.assertIn("敵陣支配度 (Field Tilt): FC東京 62.5%", prompt)
        self.assertIn("仲川 輝人", prompt)
        self.assertIn("松橋 力蔵", prompt)
        self.assertIn("6-0", prompt)

    def test_extract_with_mock_client(self) -> None:
        """モックを用いた抽出実行とJSON保存テスト."""
        mock_response = json.dumps({
            "match_id": self.sample_id,
            "home_formation": "4-4-2",
            "away_formation": "4-4-2",
            "tactical_highlights": ["右サイドの攻略", "ロングカウンター", "交代策の的中"],
            "phases": [
                {
                    "phase": "0-15",
                    "dominant_team": "EQUAL",
                    "momentum_summary": "ハイプレスとビルドアップの探り合い",
                    "pressing_battle": "前線からのプレス合戦",
                    "tactical_adjustments": "立ち上がりの指示",
                },
            ],
            "key_tactical_events": [
                {
                    "minute": 32,
                    "period": "1H",
                    "team_side": "HOME",
                    "category": "CHANCE_CREATION",
                    "actors": ["仲川 輝人"],
                    "zone": "右ポケット",
                    "description": "ヘディングで先制",
                },
            ],
        }, ensure_ascii=False)

        mock_genai = MagicMock()
        mock_genai.generate.return_value = f"```json\n{mock_response}\n```"

        enricher = TacticalEnricher(gemini_client=mock_genai)
        result = enricher.extract_tactical_structure(
            self.sample_id,
            match_id_synonym="20261025_FCT_MIT",
        )

        self.assertEqual(result["match_id"], self.sample_id)
        self.assertEqual(len(result["tactical_highlights"]), 3)
        self.assertIn("deep_metrics", result)


if __name__ == "__main__":
    unittest.main()
