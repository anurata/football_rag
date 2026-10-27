"""
tests/test_notebooklm_exporter.py

Unit tests for Google NotebookLM tactical knowledge exporter.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.export_notebooklm import NotebookLMExporter


class TestNotebookLMExporter(unittest.TestCase):
    """Test suite for NotebookLMExporter."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.test_dir) / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy knowledge dir
        self.knowledge_dir = Path(self.test_dir) / "knowledge"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        (self.knowledge_dir / "tactical_tradeoffs.yaml").write_text(
            "tradeoffs:\n  - tactic_name: 'ハイライン・ハイプレス'\n    core_mechanism: '敵陣でのボール奪取'\n    side_effects:\n      - risk_name: '背後スペース露呈'\n",
            encoding="utf-8",
        )
        (self.knowledge_dir / "metric_causal_trees.yaml").write_text(
            "trees:\n  - metric_name: '進入変換率'\n    phenomenon: '30mからPAへの侵入効率'\n    hypotheses:\n      - name: 'ポケット侵入の連動'\n",
            encoding="utf-8",
        )

        # Create dummy structured dir
        self.structured_dir = Path(self.test_dir) / "structured"
        self.structured_dir.mkdir(parents=True, exist_ok=True)
        dummy_match = {
            "match_id": "20260808_FCT_TEST",
            "home_formation": "4-2-3-1",
            "away_formation": "4-4-2",
            "tactical_highlights": ["電撃先制ゴール", "中盤の攻防"],
            "phases": [
                {
                    "phase": "0-15",
                    "dominant_team": "HOME",
                    "momentum_summary": "ホームが攻勢",
                    "pressing_battle": "前線プレスが奏功",
                    "tactical_adjustments": "立ち位置の修正",
                },
            ],
            "deep_metrics": {
                "conversion_rates": {
                    "home": {"rate_30_to_pa": 25.0, "rate_pa_to_shot": 50.0},
                    "away": {"rate_30_to_pa": 15.0, "rate_pa_to_shot": 40.0},
                },
                "field_tilt": {"home_field_tilt": 60.0, "away_field_tilt": 40.0},
            },
        }
        (self.structured_dir / "20260808_FCT_TEST_tactical.json").write_text(
            json.dumps(dummy_match, ensure_ascii=False),
            encoding="utf-8",
        )

        self.exporter = NotebookLMExporter(
            db_path="data/football.db",
            structured_dir=str(self.structured_dir),
            knowledge_dir=str(self.knowledge_dir),
            output_dir=str(self.output_dir),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_export_tactical_knowledge(self) -> None:
        """Verify tactical knowledge markdown generation."""
        out_file = self.exporter.export_tactical_knowledge()
        self.assertIsNotNone(out_file)
        self.assertTrue(out_file.exists())

        content = out_file.read_text(encoding="utf-8")
        self.assertIn("# Jリーグ戦術分析ナレッジ体系＆理論ベース", content)
        self.assertIn("ハイプレス", content)
        self.assertIn("進入変換率", content)

    def test_format_single_match_section(self) -> None:
        """Verify single match section formatting with dummy structured data."""
        dummy_match_meta = {
            "match_id": "20260808_FCT_TEST",
            "home_team_id": "FCT",
            "away_team_id": "ZEL",
            "home_score": 2,
            "away_score": 1,
            "matchweek": 1,
            "date": "2026-08-08",
            "stadium": "味の素スタジアム",
            "weather": "晴れ",
            "attendance": 25000,
        }
        structured_data = self.exporter._load_structured_json("20260808_FCT_TEST")
        self.assertIsNotNone(structured_data)

        md = self.exporter._format_single_match_section(dummy_match_meta, structured_data)
        self.assertIn("FC東京 2 - 1 町田ゼルビア", md)
        self.assertIn("4-2-3-1", md)
        self.assertIn("電撃先制ゴール", md)
        self.assertIn("ホームが攻勢", md)

    def test_format_deep_metrics_table(self) -> None:
        """Verify markdown table for deep metrics."""
        metrics = {
            "conversion_rates": {
                "home": {
                    "m30_count": 50,
                    "pa_count": 10,
                    "rate_30_to_pa": 20.0,
                    "rate_pa_to_shot": 50.0,
                },
                "away": {
                    "m30_count": 40,
                    "pa_count": 5,
                    "rate_30_to_pa": 12.5,
                    "rate_pa_to_shot": 40.0,
                },
            },
            "field_tilt": {
                "home_field_tilt": 55.0,
                "away_field_tilt": 45.0,
            },
        }
        table = self.exporter._format_deep_metrics_table(metrics, "FC東京", "町田ゼルビア")
        self.assertIn("| 敵陣支配率 (Field Tilt) | 55.0% | 45.0% |", table)
        self.assertIn("| 進入変換率 (30m->PA) | 20.0% | 12.5% |", table)

    def test_export_prompt_guide(self) -> None:
        """Verify prompt guide generation."""
        out_file = self.exporter.export_prompt_guide()
        self.assertTrue(out_file.exists())
        content = out_file.read_text(encoding="utf-8")
        self.assertIn("NotebookLM", content)
        self.assertIn("プロンプト", content)


if __name__ == "__main__":
    unittest.main()
