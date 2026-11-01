# -*- coding: utf-8 -*-
"""
Tests for Preview Curation Service (tests/test_preview_curation_service.py).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from pipeline.preview_curation_service import PreviewCurationService


class TestPreviewCurationService(unittest.TestCase):
    """Unit tests for PreviewCurationService."""

    def setUp(self) -> None:
        self.mock_extractor = MagicMock()
        self.mock_facts = {
            "basic_info": {
                "matchweek": 13,
                "home_team_name": "ファジアーノ岡山",
                "away_team_name": "FC東京",
                "date": "2026-10-31",
                "kickoff": "14:00",
                "stadium": "シティライトスタジアム",
                "weather_forecast": "晴れ / 20℃",
            },
            "home_team": {
                "team_id": "OKA",
                "manager": {"name": "木山 隆之"},
                "record": {"played": 12, "wins": 6, "draws": 4, "losses": 2},
                "avg_stats": {"goals_scored": 1.4, "goals_conceded": 0.8},
                "injuries": [],
                "lineup_prediction": {
                    "formation": "3-4-2-1",
                    "predicted_starters": [{"name": "ルカオ", "pos": "FW"}],
                    "predicted_bench": [{"name": "江坂 任", "pos": "MF"}],
                },
            },
            "away_team": {
                "team_id": "FCT",
                "manager": {"name": "ピーター クラモフスキー"},
                "record": {"played": 12, "wins": 9, "draws": 3, "losses": 0},
                "avg_stats": {"goals_scored": 2.1, "goals_conceded": 0.5},
                "injuries": [],
                "lineup_prediction": {
                    "formation": "4-2-1-3",
                    "predicted_starters": [{"name": "仲川 輝人", "pos": "FW"}],
                    "predicted_bench": [{"name": "俵積田 晃太", "pos": "FW"}],
                },
            },
        }
        self.mock_extractor.extract_match_preview_facts.return_value = self.mock_facts
        self.service = PreviewCurationService(fact_extractor=self.mock_extractor)

    def test_generate_curation_workspace(self) -> None:
        workspace = self.service.generate_curation_workspace(
            home_team_id="OKA",
            away_team_id="FCT",
            match_date="2026-10-31",
            matchweek=13,
        )
        self.assertIn("facts", workspace)
        self.assertIn("branches", workspace)
        branches = workspace["branches"]
        self.assertEqual(len(branches), 4)

        branch_ids = [b["branch_id"] for b in branches]
        self.assertIn("lineup_home", branch_ids)
        self.assertIn("lineup_away", branch_ids)
        self.assertIn("tactical_scenario", branch_ids)
        self.assertIn("matchup_focus", branch_ids)

        for b in branches:
            self.assertGreaterEqual(len(b["options"]), 2)
            for opt in b["options"]:
                self.assertTrue(opt["fact_basis"].startswith("【事実】"))
                self.assertTrue(opt["inference"].startswith("【推測】"))

    def test_compile_curated_report_and_save(self) -> None:
        selections = {
            "【スタメン予想】ファジアーノ岡山 の布陣・先発選定": "選択案 [A] 前節継続",
        }
        custom_note = "木山監督の守備ブロックに対し、立ち上がりの失点回避が最優先。"

        curated_md = self.service.compile_curated_report(
            facts=self.mock_facts,
            selections=selections,
            custom_insights=custom_note,
        )

        self.assertIn("2026明治安田J1リーグ 第13節 プレビューレポート", curated_md)
        self.assertIn("共同キュレーション確定セクション（Curated Focus）", curated_md)
        self.assertIn("選択案 [A] 前節継続", curated_md)
        self.assertIn(custom_note, curated_md)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "test_preview_curated.md"
            self.service.save_curated_report(out_path, curated_md)
            self.assertTrue(out_path.exists())
            self.assertEqual(out_path.read_text(encoding="utf-8"), curated_md)


if __name__ == "__main__":
    unittest.main()
