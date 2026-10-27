"""Unit tests for FC Tokyo 2026 Raw Match Data Integrity Validation (tests/test_fct_raw_validation.py).

Verifies that all 12 FC Tokyo matches in the 2026 season have authentic,
complete raw data (SPAIA, Football LAB, Yahoo) meeting specification thresholds.
"""

import os
import unittest
from pathlib import Path

from pipeline.data_validator import (
    InvalidRawDataError,
    validate_football_lab_data,
    validate_match_data_bundle,
    validate_spaia_comments,
    validate_spaia_player_stats,
    validate_yahoo_text,
)

# FC東京 2026シーズン 正真正銘公式ID群
FCT_CANONICAL_GAME_IDS = [
    "2026080802",  # MW1: FCT vs ZEL (1-5)
    "2026081508",  # MW2: VOB vs FCT (2-2)
    "2026082101",  # MW3: FCT vs JEF (2-0)
    "2026082904",  # MW4: VVN vs FCT (0-3)
    "2026090221",  # MW5: PUL vs FCT (1-1)
    "2026090610",  # MW6: FCT vs SAN (2-0)
    "2026091204",  # MW7: GAM vs FCT (0-2)
    "2026091902",  # MW8: FCT vs NAG (1-0)
    "2026101009",  # MW9: FCT vs URA (3-0)
    "2026101708",  # MW10: VER vs FCT (0-4)
    "2026102108",  # MW11: FCT vs REY (0-0)
    "2026102505",  # MW12: FCT vs MIT (6-0)
]

FCT_CANONICAL_MATCH_IDS = [
    "20260808_FCT_ZEL",
    "20260815_VOB_FCT",
    "20260821_FCT_JEF",
    "20260829_VVN_FCT",
    "20260902_PUL_FCT",
    "20260906_FCT_SAN",
    "20260912_GAM_FCT",
    "20260919_FCT_NAG",
    "20261010_FCT_URA",
    "20261017_VER_FCT",
    "20261021_FCT_REY",
    "20261025_FCT_MIT",
]


class TestFCTRawValidation(unittest.TestCase):
    """FC東京全12試合の生データ完全性テストスイート."""

    def test_all_12_fct_matches_pass_validation(self) -> None:
        """全12試合の生データバンドル（公式GameIDおよびMatchID）がバリデーションを満たすことを検証する."""
        all_ids = FCT_CANONICAL_GAME_IDS + FCT_CANONICAL_MATCH_IDS
        for target_id in all_ids:
            with self.subTest(target_id=target_id):
                result = validate_match_data_bundle(target_id)
                self.assertEqual(result["game_id"], target_id)

                # 1. SPAIA 選手詳細スタッツ
                spaia_stats = result["spaia_player_stats"]
                players = spaia_stats.get("player_stats", [])
                self.assertGreaterEqual(
                    len(players),
                    20,
                    f"{target_id}: 登録選手数が不足しています",
                )
                self.assertIn("Name", players[0])
                self.assertIn("Pos", players[0])
                self.assertIn("At3rdPlayCount", players[0])

                # 2. SPAIA コメント
                spaia_comments = result["spaia_comments"]
                comments = spaia_comments.get("comments", [])
                self.assertGreaterEqual(
                    len(comments),
                    40,
                    f"{target_id}: コメント数が不足しています",
                )

                # 3. Football LAB
                flab = result["football_lab"]["data"]
                cbp_matrix = flab.get("cbp", {}).get("player_matrix", [])
                self.assertGreaterEqual(
                    len(cbp_matrix),
                    20,
                    f"{target_id}: CBP選手数が不足しています",
                )
                self.assertGreaterEqual(
                    len(flab.get("timeline_blocks", [])),
                    6,
                    f"{target_id}: タイムラインブロックが6フェーズ未満です",
                )

                # 4. Yahoo! テキスト速報
                yahoo_text = result["yahoo_text"]
                timeline = yahoo_text.get("timeline", [])
                self.assertGreaterEqual(
                    len(timeline),
                    40,
                    f"{target_id}: Yahooタイムラインが不足しています",
                )

    def test_dummy_file_triggers_validation_error(self) -> None:
        """ダミーや不完全なデータがFail-Fastで弾かれることを検証する."""
        dummy_path = "scratch/dummy_test_stats.json"
        os.makedirs("scratch", exist_ok=True)
        try:
            with open(dummy_path, "w", encoding="utf-8") as f:
                f.write('{"stats_summary": "dummy"}')

            with self.assertRaises(InvalidRawDataError):
                validate_spaia_player_stats(dummy_path)
        finally:
            if os.path.exists(dummy_path):
                os.remove(dummy_path)


if __name__ == "__main__":
    unittest.main()
