"""
Unit tests for PreviewFactExtractor (tests/test_preview_fact_extractor.py).
Validates deterministic factual extraction without hallucinations.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.preview_fact_extractor import PreviewFactExtractor

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "football.db"


class TestPreviewFactExtractor(unittest.TestCase):
    """Test deterministic factual preview extraction."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.extractor = PreviewFactExtractor(db_path=DB_PATH)

    def test_extract_match_preview_facts_basic_info(self) -> None:
        """Test basic metadata extraction for OKA vs FCT."""
        facts = self.extractor.extract_match_preview_facts(
            home_team_id="OKA",
            away_team_id="FCT",
            match_date="2026-10-31",
            matchweek=13,
        )

        basic = facts.get("basic_info", {})
        self.assertEqual(basic.get("matchweek"), 13)
        self.assertEqual(basic.get("date"), "2026-10-31")
        self.assertEqual(basic.get("home_team_id"), "OKA")
        self.assertEqual(basic.get("away_team_id"), "FCT")
        self.assertIn("シティライトスタジアム", basic.get("stadium", ""))

    def test_extract_fct_lineup_and_injuries(self) -> None:
        """Verify that FCT lineup excludes injured players and sets correct GK."""
        facts = self.extractor.extract_match_preview_facts(
            home_team_id="OKA",
            away_team_id="FCT",
            match_date="2026-10-31",
            matchweek=13,
        )

        away = facts.get("away_team", {})
        self.assertEqual(away.get("team_id"), "FCT")

        # Verify manager
        self.assertEqual(away.get("manager", {}).get("name"), "松橋 力蔵")

        # Verify injury list contains Muroya Sei
        inj_names = [inj["player_name"] for inj in away.get("injuries", [])]
        self.assertIn("室屋 成", inj_names)

        # Verify predicted lineup slots
        lineup = away.get("predicted_lineup", [])
        self.assertEqual(len(lineup), 11)

        slot_map = {item["slot_id"]: item["player_name"] for item in lineup}

        # GK must be Kim Seung-gyu, NOT Hatano
        self.assertEqual(slot_map.get("GK"), "キム スンギュ")

        # RSB must NOT be Muroya (he is injured), should be Ishihara
        self.assertNotEqual(slot_map.get("RSB"), "室屋 成")
        self.assertEqual(slot_map.get("RSB"), "石原 広教")

        # Check Center Backs
        self.assertEqual(slot_map.get("RCB"), "アレクサンダー ショルツ")
        self.assertEqual(slot_map.get("LCB"), "稲村 隼翔")

        # Check Side Midfielders
        self.assertEqual(slot_map.get("RSH"), "安斎 颯馬")
        self.assertEqual(slot_map.get("LSH"), "佐藤 恵允")

    def test_extract_oka_lineup_and_patterns(self) -> None:
        """Verify OKA factual profile contains Lucao and winning patterns."""
        facts = self.extractor.extract_match_preview_facts(
            home_team_id="OKA",
            away_team_id="FCT",
            match_date="2026-10-31",
            matchweek=13,
        )

        home = facts.get("home_team", {})
        self.assertEqual(home.get("team_id"), "OKA")
        self.assertEqual(home.get("manager", {}).get("name"), "木山 隆之")

        # Verify stats exist
        avg_stats = home.get("avg_stats", {})
        self.assertIn("possession_pct", avg_stats)
        self.assertIn("sprints_per_game", avg_stats)

        # Verify winning patterns exist
        win_patterns = home.get("winning_patterns", [])
        self.assertGreater(len(win_patterns), 0)


if __name__ == "__main__":
    unittest.main()

