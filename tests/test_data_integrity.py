"""データ完全性バリデーションのユニットテスト (Data Integrity Tests)."""

import os
import unittest

from pipeline.data_validator import (
    InvalidRawDataError,
    validate_football_lab_data,
    validate_match_data_bundle,
    validate_spaia_comments,
    validate_spaia_player_stats,
    validate_yahoo_text,
)


class TestDataIntegrity(unittest.TestCase):
    """生データ完全性バリデータのテストクラス."""

    REAL_GAME_ID = "2026102505"
    DUMMY_MATCH_ID = "20260815_URA_HIR"

    def test_real_data_bundle_passes(self) -> None:
        """成功事例（東京水戸戦: 2026102505）の実データセットが全件合格することを検証."""
        res = validate_match_data_bundle(self.REAL_GAME_ID)
        self.assertEqual(res["game_id"], self.REAL_GAME_ID)
        self.assertIn("player_stats", res["spaia_player_stats"])
        self.assertIn("comments", res["spaia_comments"])
        self.assertIn("data", res["football_lab"])
        self.assertIn("timeline", res["yahoo_text"])

    def test_dummy_spaia_player_stats_rejected(self) -> None:
        """786バイトの簡易ダミーファイル（20260815_URA_HIR）が確実に弾かれることを検証."""
        dummy_path = os.path.join(
            "data",
            "raw",
            "spaia",
            f"{self.DUMMY_MATCH_ID}_player_stats.json",
        )
        if os.path.exists(dummy_path):
            with self.assertRaises(InvalidRawDataError) as ctx:
                validate_spaia_player_stats(dummy_path)
            # エラーメッセージにサイズ不足またはダミー形式の警告が含まれていること
            err_msg = str(ctx.exception)
            self.assertTrue(
                "ファイルサイズが不足しています" in err_msg or "stats_summary" in err_msg,
                f"Unexpected error message: {err_msg}",
            )

    def test_nonexistent_file_rejected(self) -> None:
        """存在しないファイルパスが正しく InvalidRawDataError として検出されることを検証."""
        fake_path = "data/raw/spaia/nonexistent_game_player_stats.json"
        with self.assertRaises(InvalidRawDataError) as ctx:
            validate_spaia_player_stats(fake_path)
        self.assertIn("ファイルが存在しません", str(ctx.exception))

    def test_real_spaia_player_stats_keys(self) -> None:
        """本物のSPAIA選手スタッツの必須キーがすべて揃っていることを個別検証."""
        real_path = os.path.join(
            "data",
            "raw",
            "spaia",
            f"{self.REAL_GAME_ID}_player_stats.json",
        )
        data = validate_spaia_player_stats(real_path)
        players = data["player_stats"]
        self.assertGreaterEqual(len(players), 28)
        first_player = players[0]
        self.assertIn("Uni", first_player)
        self.assertIn("At3rdPlayCount", first_player)
        self.assertIn("M30PlayCount", first_player)
        self.assertIn("PAPlayCount", first_player)

    def test_real_football_lab_cbp_keys(self) -> None:
        """本物のFootball LABのCBPマトリクスがすべて揃っていることを個別検証."""
        real_path = os.path.join(
            "data",
            "raw",
            "football_lab",
            f"{self.REAL_GAME_ID}.json",
        )
        data = validate_football_lab_data(real_path)
        matrix = data["data"]["cbp"]["player_matrix"]
        self.assertGreaterEqual(len(matrix), 28)
        first_p = matrix[0]
        self.assertIn("attack", first_p)
        self.assertIn("defense", first_p)
        self.assertIn("gain", first_p)

    def test_real_yahoo_text_flags(self) -> None:
        """本物のYahoo速報タイムラインに構造化フラグが存在することを個別検証."""
        real_path = os.path.join(
            "data",
            "raw",
            "yahoo",
            f"{self.REAL_GAME_ID}_text.json",
        )
        data = validate_yahoo_text(real_path)
        timeline = data["timeline"]
        self.assertGreaterEqual(len(timeline), 50)
        first_event = timeline[0]
        self.assertIn("is_goal", first_event)
        self.assertIn("is_card", first_event)
        self.assertIn("is_substitution", first_event)


if __name__ == "__main__":
    unittest.main()
