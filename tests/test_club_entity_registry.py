"""
tests/test_club_entity_registry.py

Unit tests for J1 all-20-club ground-truth registry and dynamic
FC Tokyo Emperor's Cup opponent registration.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.club_entity_registry import ClubEntityRegistry


class TestClubEntityRegistry(unittest.TestCase):
    """Test suite for ClubEntityRegistry."""

    def test_j1_2026_all_20_clubs_and_official_managers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "target_clubs.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "include_all_j1_2026": True,
                        "fct_emperor_cup_opponents": [],
                    },
                ),
                encoding="utf-8",
            )

            registry = ClubEntityRegistry(target_config_path=cfg_path)
            clubs = registry.list_target_clubs()
            self.assertEqual(len(clubs), 20)

            fct = registry.get_club("FCT")
            kas = registry.get_club("KAS")
            ura = registry.get_club("URA")
            vob = registry.get_club("VOB")
            ver = registry.get_club("VER")

            self.assertIsNotNone(fct)
            self.assertEqual(fct["current_manager"], "松橋 力蔵")
            self.assertEqual(kas["current_manager"], "鬼木 達")
            self.assertEqual(ura["current_manager"], "曺 貴裁")
            self.assertEqual(vob["current_manager"], "ミヒャエル スキッベ")

            # Tokyo Verdy had a 2026 mid-season change: 城福 浩 -> 相馬 直樹
            self.assertEqual(ver["current_manager"], "相馬 直樹")
            self.assertIn("城福 浩", ver["previous_managers_2026"])

    def test_register_fct_emperor_cup_non_j1_opponent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "target_clubs.json"
            registry = ClubEntityRegistry(target_config_path=cfg_path)

            entry = registry.register_emperor_cup_opponent(
                team_id="VEG",
                canonical_name="ベガルタ仙台",
                short_name="仙台",
                category="J2",
                current_manager="森山 佳郎",
                key_players=["郷家 友太", "相良 竜之介"],
                round_label="天皇杯3回戦",
                persist_to_config=True,
            )

            self.assertEqual(entry["team_id"], "VEG")
            self.assertTrue(entry["is_fct_emperor_cup_opponent"])
            self.assertEqual(len(registry.list_target_clubs()), 21)

            # Reload from persisted config and confirm persistence
            reloaded = ClubEntityRegistry(target_config_path=cfg_path)
            veg = reloaded.get_club("VEG")
            self.assertIsNotNone(veg)
            self.assertEqual(veg["current_manager"], "森山 佳郎")

            # Confirm multi-club detection picks up both FCT and Emperor's Cup opponent
            detected = reloaded.detect_mentioned_clubs(
                title="【天皇杯プレビュー】FC東京 vs ベガルタ仙台 徹底展望",
                transcript_text="松橋監督のFC東京に対して森山監督率いる仙台がハイプレスで挑む。",
            )
            self.assertIn("FCT", detected)
            self.assertIn("VEG", detected)


if __name__ == "__main__":
    unittest.main()

