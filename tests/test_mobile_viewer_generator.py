# -*- coding: utf-8 -*-
"""
tests/test_mobile_viewer_generator.py

Unit tests for MobileViewerGenerator.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.generate_mobile_viewer import MobileViewerGenerator


class TestMobileViewerGenerator(unittest.TestCase):
    """Test suite for MobileViewerGenerator."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.test_dir) / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.structured_dir = Path(self.test_dir) / "structured"
        self.structured_dir.mkdir(parents=True, exist_ok=True)

        dummy_match = {
            "match_id": "20260808_FCT_TEST",
            "home_formation": "4-2-3-1",
            "away_formation": "4-4-2",
            "tactical_highlights": ["先制ゴール"],
        }
        (self.structured_dir / "20260808_FCT_TEST_tactical.json").write_text(
            json.dumps(dummy_match, ensure_ascii=False),
            encoding="utf-8",
        )

        self.generator = MobileViewerGenerator(
            db_path="data/football.db",
            structured_dir=str(self.structured_dir),
            output_dir=str(self.output_dir),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_generate_html_and_markdown(self) -> None:
        """Verify progressive mobile viewer HTML and Markdown generation."""
        out_file = self.generator.generate()
        self.assertTrue(out_file.exists())

        content = out_file.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("J1戦術カルテ", content)
        self.assertIn("MATCHES", content)
        self.assertIn("match-details", content)
        self.assertIn("mw-section", content)
        self.assertIn("pills-container", content)


if __name__ == "__main__":
    unittest.main()
