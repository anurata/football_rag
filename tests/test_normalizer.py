"""
Unit tests for pipeline/normalizer.py.
"""

import unittest
from pipeline.normalizer import (
    EntityNormalizer,
    compute_game_state,
    build_match_id,
)


class TestEntityNormalizer(unittest.TestCase):
    """Test team and player entity resolution."""

    @classmethod
    def setUpClass(cls):
        cls.normalizer = EntityNormalizer()

    def test_team_normalization_fctokyo(self):
        """Test variations of FC Tokyo resolve to FCT."""
        variations = [
            "ＦＣ東京",
            "FC東京",
            "FC Tokyo",
            "東京",
            "F.C.TOKYO",
        ]
        for name in variations:
            self.assertEqual(
                self.normalizer.normalize_team_name(name),
                "FCT",
                f"Failed for: {name}",
            )

    def test_team_normalization_kashima(self):
        """Test variations of Kashima Antlers resolve to KAS."""
        variations = [
            "鹿島アントラーズ",
            "鹿島",
            "Kashima Antlers",
        ]
        for name in variations:
            self.assertEqual(
                self.normalizer.normalize_team_name(name),
                "KAS",
                f"Failed for: {name}",
            )

    def test_team_normalization_others(self):
        """Test resolution for Gamba, Kawasaki, Mito."""
        self.assertEqual(self.normalizer.normalize_team_name("ガンバ大阪"), "GAM")
        self.assertEqual(self.normalizer.normalize_team_name("G大阪"), "GAM")
        self.assertEqual(self.normalizer.normalize_team_name("川崎フロンターレ"), "KAW")
        self.assertEqual(self.normalizer.normalize_team_name("川崎F"), "KAW")
        self.assertEqual(self.normalizer.normalize_team_name("水戸ホーリーホック"), "MIT")
        self.assertEqual(self.normalizer.normalize_team_name("水戸"), "MIT")

    def test_unknown_team(self):
        """Test unknown team returns None."""
        self.assertIsNone(self.normalizer.normalize_team_name("存在しないチーム名"))

    def test_player_normalization(self):
        """Test space and alias normalization for registered players."""
        # Nagatomo
        pid, name = self.normalizer.normalize_player_name("長友 佑都", "FCT")
        self.assertEqual(pid, "P_FCT_NAGATOMO")
        self.assertEqual(name, "長友 佑都")

        pid2, name2 = self.normalizer.normalize_player_name("長友佑都")
        self.assertEqual(pid2, "P_FCT_NAGATOMO")

        # Unknown player preserves cleaned formatting
        pid_un, name_un = self.normalizer.normalize_player_name("ディエゴ オリヴェイラ")
        self.assertIsNone(pid_un)
        self.assertEqual(name_un, "ディエゴ オリヴェイラ")

    def test_compute_game_state(self):
        """Test score state computation for home and away."""
        # 0-0 Draw
        self.assertEqual(compute_game_state(0, 0, is_home=True), "DRAW")
        self.assertEqual(compute_game_state(0, 0, is_home=False), "DRAW")

        # 2-1 Home leads
        self.assertEqual(compute_game_state(2, 1, is_home=True), "LEADING")
        self.assertEqual(compute_game_state(2, 1, is_home=False), "TRAILING")

        # 0-2 Away leads
        self.assertEqual(compute_game_state(0, 2, is_home=True), "TRAILING")
        self.assertEqual(compute_game_state(0, 2, is_home=False), "LEADING")

    def test_build_match_id(self):
        """Test standardized match_id creation."""
        mid1 = build_match_id("2026-10-21", "FCT", "KAS")
        self.assertEqual(mid1, "20261021_FCT_KAS")

        mid2 = build_match_id("2026/10/25", "FCT", "MIT")
        self.assertEqual(mid2, "20261025_FCT_MIT")


if __name__ == "__main__":
    unittest.main()
