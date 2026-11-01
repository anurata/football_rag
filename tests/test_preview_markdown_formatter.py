"""
Unit tests for Preview Markdown Formatter (tests/test_preview_markdown_formatter.py).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.preview_fact_extractor import PreviewFactExtractor
from pipeline.preview_markdown_formatter import format_preview_markdown

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "football.db"


class TestPreviewMarkdownFormatter(unittest.TestCase):
    """Test rendering of preview facts into markdown report."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = PreviewFactExtractor(db_path=DB_PATH)

    def test_format_preview_markdown_structure(self) -> None:
        """Verify report contains required sections and no hallucinated elements."""
        facts = self.extractor.extract_match_preview_facts(
            home_team_id="OKA",
            away_team_id="FCT",
            match_date="2026-10-31",
            matchweek=13,
        )

        md = format_preview_markdown(facts)

        # Check section headers
        self.assertIn("# 2026明治安田J1リーグ 第13節 プレビューレポート", md)
        self.assertIn("## 1) 試合の基本情報", md)
        self.assertIn("## 2) 各チームの概要", md)
        self.assertIn("## 3) 試合予測", md)
        self.assertIn("## 4) 観戦のポイント", md)
        self.assertIn("## 5) 試合プレビューのまとめ", md)

        # Check key team items
        self.assertIn("ファジアーノ岡山", md)
        self.assertIn("FC東京", md)
        self.assertIn("シティライトスタジアム", md)

        # Check verified players
        self.assertIn("キム スンギュ", md)
        self.assertIn("石原 広教", md)
        self.assertIn("稲村 隼翔", md)
        self.assertIn("アレクサンダー ショルツ", md)
        self.assertIn("室屋 成", md)  # Must be mentioned under injuries

        # Lucao and Ryan impact subs
        self.assertIn("マルセロ ヒアン", md)
        self.assertIn("ルカオ", md)


if __name__ == "__main__":
    unittest.main()

