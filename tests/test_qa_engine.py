"""
tests/test_qa_engine.py

Unit tests for TacticalQAEngine and its Google Search Grounding integration.
"""

import unittest
from pathlib import Path

from agent.gemini_client import GeminiTacticalClient
from agent.qa_engine import TacticalQAEngine


class TestTacticalQAEngine(unittest.TestCase):
    """Test suite for TacticalQAEngine."""

    def setUp(self) -> None:
        """Set up mock QA engine instance."""
        self.client = GeminiTacticalClient(mock_mode=True)
        self.engine = TacticalQAEngine(
            gemini_client=self.client,
            db_path="data/football.db",
            structured_dir="data/structured",
            mock_mode=True,
        )

    def test_ask_global_without_match(self) -> None:
        """Verify global question answering returns expected dictionary structure."""
        res = self.engine.ask(
            question="2026年シーズンのFC東京の基本戦術はどうなっていますか？",
            match_id=None,
            enable_web_search=False,
        )

        self.assertIn("question", res)
        self.assertIn("answer", res)
        self.assertIn("web_search_enabled", res)
        self.assertFalse(res["web_search_enabled"])
        self.assertIn("model_used", res)
        self.assertIn("QA回答（モック）", res["answer"])
        self.assertEqual(len(res["grounding_sources"]), 0)

    def test_ask_with_web_search_enabled(self) -> None:
        """Verify web search flag triggers search sources in mock mode."""
        res = self.engine.ask(
            question="FC東京の最新の怪我人情報は？",
            match_id=None,
            enable_web_search=True,
        )

        self.assertTrue(res["web_search_enabled"])
        self.assertGreater(len(res["grounding_sources"]), 0)
        self.assertIn("Google検索グラウンディング", res["answer"])
        self.assertEqual(res["grounding_sources"][0]["url"], "https://www.jleague.jp/news/")

    def test_build_context_with_existing_match(self) -> None:
        """Verify context building extracts match context and tactical perspectives."""
        # Check if structured data exists
        structured_files = list(Path("data/structured").glob("*_tactical.json"))
        if structured_files:
            match_id = structured_files[0].stem.replace("_tactical", "")
            context_text, meta = self.engine._build_context(match_id)
            self.assertIsInstance(context_text, str)
            self.assertIsInstance(meta, str)
            self.assertGreater(len(context_text), 0)

    def test_format_match_context_elements(self) -> None:
        """Verify match context formatter handles injuries, schedule, and cards."""
        dummy_ctx = {
            "injuries_and_conditions": ["選手A: 離脱中", "選手B: 別メニュー",],
            "yellow_accumulation": ["選手C: 累積3枚",],
            "schedule_density": {"description": "中3日の過密日程",},
            "climate_and_pitch": {"description": "雨・重馬場",},
            "loan_restrictions": ["選手D: 出場不可",],
        }
        formatted = self.engine._format_match_context(dummy_ctx)
        self.assertIn("選手A: 離脱中", formatted)
        self.assertIn("中3日の過密日程", formatted)
        self.assertIn("雨・重馬場", formatted)
        self.assertIn("選手D: 出場不可", formatted)


if __name__ == "__main__":
    unittest.main()
