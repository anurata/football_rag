# -*- coding: utf-8 -*-
"""
Tests for scheduled pipeline runner (tests/test_run_scheduled_pipeline.py).
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from pipeline.phase_calculator import PREVIEW_DRAFT, PREVIEW_FINAL, STAGE1, STAGE2
from scripts.run_scheduled_pipeline import ScheduledPipelineRunner


class TestScheduledPipelineRunner(unittest.TestCase):
    """Unit tests for ScheduledPipelineRunner."""

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.exports_dir = Path(self.temp_dir.name) / "exports"
        self.markdown_dir = Path(self.temp_dir.name) / "markdown"
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.markdown_dir.mkdir(parents=True, exist_ok=True)

        self.runner = ScheduledPipelineRunner(
            db_path=":memory:",
            exports_dir=self.exports_dir,
            markdown_dir=self.markdown_dir,
            dry_run=False,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dry_run_bypasses_execution(self) -> None:
        """Dry run should return True without creating actual files."""
        dry_runner = ScheduledPipelineRunner(
            db_path=":memory:",
            exports_dir=self.exports_dir,
            markdown_dir=self.markdown_dir,
            dry_run=True,
        )
        sample_match = {
            "match_id": "20261031_OKA_FCT",
            "home": "OKA",
            "away": "FCT",
            "kickoff": "2026-10-31T14:00:00+09:00",
            "matchweek": 13,
        }

        self.assertTrue(dry_runner.execute_phase(sample_match, PREVIEW_DRAFT))
        self.assertTrue(dry_runner.execute_phase(sample_match, PREVIEW_FINAL))
        self.assertTrue(dry_runner.execute_phase(sample_match, STAGE1))
        self.assertTrue(dry_runner.execute_phase(sample_match, STAGE2))

        # Check that no preview files were written
        self.assertFalse((self.exports_dir / "20261031_OKA_FCT_preview_auto.md").exists())

    @patch("scripts.run_scheduled_pipeline.format_preview_markdown")
    @patch("scripts.run_scheduled_pipeline.PreviewFactExtractor")
    def test_run_preview_draft_success(
        self,
        mock_extractor_cls: MagicMock,
        mock_formatter: MagicMock,
    ) -> None:
        """Preview draft should extract facts and save formatted markdown."""
        mock_extractor = MagicMock()
        mock_extractor.extract_match_preview_facts.return_value = {"mock": "fact"}
        mock_extractor_cls.return_value = mock_extractor
        mock_formatter.return_value = "# Mock Preview Markdown"

        sample_match = {
            "match_id": "20261031_OKA_FCT",
            "home": "OKA",
            "away": "FCT",
            "kickoff": "2026-10-31T14:00:00+09:00",
            "matchweek": 13,
        }

        success = self.runner.run_preview_draft(sample_match)
        self.assertTrue(success)

        out_file = self.exports_dir / "20261031_OKA_FCT_preview_auto.md"
        self.assertTrue(out_file.exists())
        self.assertIn("# Mock Preview Markdown", out_file.read_text(encoding="utf-8"))

    @patch("scripts.run_scheduled_pipeline.format_preview_markdown")
    @patch("scripts.run_scheduled_pipeline.PreviewFactExtractor")
    def test_run_preview_final_success(
        self,
        mock_extractor_cls: MagicMock,
        mock_formatter: MagicMock,
    ) -> None:
        """Preview final should create notebooklm export file."""
        mock_extractor = MagicMock()
        mock_extractor_cls.return_value = mock_extractor
        mock_formatter.return_value = "# Final Facts"

        sample_match = {
            "match_id": "20261031_OKA_FCT",
            "home": "OKA",
            "away": "FCT",
            "kickoff": "2026-10-31T14:00:00+09:00",
            "matchweek": 13,
        }

        success = self.runner.run_preview_final(sample_match)
        self.assertTrue(success)

        out_file = self.exports_dir / "notebooklm" / "20261031_OKA_FCT_notebooklm.md"
        self.assertTrue(out_file.exists())
        content = out_file.read_text(encoding="utf-8")
        self.assertIn("NotebookLM Ingestion Document", content)

    @patch("scripts.run_scheduled_pipeline.MatchweekUpdater")
    def test_run_stage_success(self, mock_updater_cls: MagicMock) -> None:
        """Stage execution should delegate to MatchweekUpdater."""
        mock_updater = MagicMock()
        mock_updater_cls.return_value = mock_updater

        sample_match = {
            "match_id": "20261031_OKA_FCT",
            "home": "OKA",
            "away": "FCT",
            "kickoff": "2026-10-31T14:00:00+09:00",
            "matchweek": 13,
        }

        success = self.runner.run_stage(sample_match, stage=1)
        self.assertTrue(success)
        mock_updater.update_from_directory.assert_called_once()
        mock_updater.close.assert_called_once()

    def test_run_plan_summary(self) -> None:
        """Plan execution collects counts and per-phase results."""
        plan = [
            {
                "match_id": "20261031_OKA_FCT",
                "home": "OKA",
                "away": "FCT",
                "kickoff": "2026-10-31T14:00:00+09:00",
                "matchweek": 13,
                "pending_phases": [PREVIEW_DRAFT, PREVIEW_FINAL],
            },
        ]

        with patch.object(self.runner, "execute_phase", side_effect=[True, False]):
            summary = self.runner.run_plan(plan)

        self.assertEqual(summary["total_matches"], 1)
        self.assertEqual(summary["executed"], 2)
        self.assertEqual(summary["succeeded"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(len(summary["details"]), 2)


if __name__ == "__main__":
    unittest.main()

