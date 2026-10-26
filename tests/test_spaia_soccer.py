"""SPAIAサッカースクレイパーの単体テスト (tests/test_spaia_soccer.py)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scrapers.spaia_soccer import SpaiasoccerScraper

SAMPLE_COMMENTS_DATA = [
    {
        "ID": 1001,
        "GameID": "2025050301",
        "CommentInfo_StateID": "0",
        "CommentInfo_StateName": "試合前",
        "CommentInfo_Half": "0",
        "CommentInfo_Comment": "両チームのスターティングメンバー発表",
        "CreatedAt": "2025-05-03T05:00:00Z",
    },
    {
        "ID": 1002,
        "GameID": "2025050301",
        "CommentInfo_StateID": "1",
        "CommentInfo_StateName": "前半",
        "CommentInfo_Half": "14",
        "CommentInfo_Comment": "広島　ペナルティエリア手前からシュートを放つもキーパーセーブ",
        "CreatedAt": "2025-05-03T05:14:00Z",
    },
    {
        "ID": 1003,
        "GameID": "2025050301",
        "CommentInfo_StateID": "1",
        "CommentInfo_StateName": "前半",
        "CommentInfo_Half": "32",
        "CommentInfo_Comment": "ゴール！！！　ヘディングで押し込んで先制！",
        "CreatedAt": "2025-05-03T05:32:00Z",
    },
]

SAMPLE_PLAYER_STATS_DATA = [
    {
        "ID": 5001,
        "GameID": "2025050301",
        "PlayerID": 1600101,
        "Name": "満田 誠",
        "NameS": "満田",
        "Uni": "11",
        "Pos": "MF",
        "TeamID": 129,
        "HV": 1,
        "StartF": "1",
        "Shoot": "3",
        "ShootOnTarget": "2",
        "Score": "1",
        "Assist": "0",
        "PassCount": "42",
        "PassRate": "78.6",
        "AtPlayRate": "35.5",
        "MtPlayRate": "50.0",
        "DtPlayRate": "14.5",
        "At3rdPlayCount": "18",
        "PAPlayCount": "4",
        "DribbleCount": "3",
        "CrossCount": "4",
        "TackleCount": "2",
        "Foul": "1",
        "Time": "90",
    },
    {
        "ID": 5002,
        "GameID": "2025050301",
        "PlayerID": 1600102,
        "Name": "大迫 敬介",
        "NameS": "大迫",
        "Uni": "1",
        "Pos": "GK",
        "TeamID": 129,
        "HV": 1,
        "StartF": "1",
        "Shoot": "0",
        "SaveCount": "3",
        "SaveRate": "100.0",
        "PassCount": "20",
        "Time": "90",
    },
]

SAMPLE_META_DATA = [
    {
        "ID": "2025050301",
        "HomeTeamName": "サンフレッチェ広島",
        "AwayTeamName": "アビスパ福岡",
        "HomeScore": "2",
        "AwayScore": "0",
        "Stadium": "エディオンピースウイング広島",
        "Attendance": "25,000",
    },
]


class TestSpaiasoccerScraper(unittest.TestCase):
    """SpaiasoccerScraperの単体テスト."""

    def setUp(self) -> None:
        """テストの初期化."""
        self.scraper = SpaiasoccerScraper()

    def test_format_comments(self) -> None:
        """コメント配列の整形ロジックを検証."""
        formatted = self.scraper._format_comments(SAMPLE_COMMENTS_DATA)

        self.assertEqual(len(formatted), 3)

        # 0番目: チーム名なし
        self.assertEqual(formatted[0]["order"], 0)
        self.assertEqual(formatted[0]["id"], 1001)
        self.assertEqual(formatted[0]["state_name"], "試合前")
        self.assertIsNone(formatted[0]["team_name"])
        self.assertEqual(
            formatted[0]["text"],
            "両チームのスターティングメンバー発表",
        )

        # 1番目: チーム名あり（「広島　...」）
        self.assertEqual(formatted[1]["order"], 1)
        self.assertEqual(formatted[1]["team_name"], "広島")
        self.assertEqual(
            formatted[1]["text"],
            "ペナルティエリア手前からシュートを放つもキーパーセーブ",
        )
        self.assertEqual(formatted[1]["half"], "14")
        self.assertEqual(formatted[1]["time_label"], "前半 (14)")

        # 2番目: ゴール実況
        self.assertEqual(formatted[2]["order"], 2)
        self.assertIn("ゴール", formatted[2]["raw_comment"])

    @patch("requests.get")
    def test_fetch_comments(self, mock_get: MagicMock) -> None:
        """fetch_commentsのAPI通信とデータ返却を検証."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_COMMENTS_DATA
        mock_get.return_value = mock_resp

        results = self.scraper.fetch_comments("2025050301")

        self.assertEqual(len(results), 3)
        self.assertEqual(results[1]["team_name"], "広島")
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_fetch_player_detail_stats(self, mock_get: MagicMock) -> None:
        """fetch_player_detail_statsのAPI通信とデータ返却を検証."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_PLAYER_STATS_DATA
        mock_get.return_value = mock_resp

        players = self.scraper.fetch_player_detail_stats("2025050301")

        self.assertEqual(len(players), 2)
        p1 = players[0]
        self.assertEqual(p1["Name"], "満田 誠")
        self.assertEqual(p1["Pos"], "MF")
        self.assertEqual(p1["Shoot"], "3")
        self.assertEqual(p1["AtPlayRate"], "35.5")

        p2 = players[1]
        self.assertEqual(p2["Name"], "大迫 敬介")
        self.assertEqual(p2["SaveRate"], "100.0")

    @patch("requests.get")
    def test_fetch_game_meta(self, mock_get: MagicMock) -> None:
        """fetch_game_metaのAPI通信とメタ情報返却を検証."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_META_DATA
        mock_get.return_value = mock_resp

        meta = self.scraper.fetch_game_meta("2025050301")

        self.assertEqual(meta["HomeTeamName"], "サンフレッチェ広島")
        self.assertEqual(meta["HomeScore"], "2")
        self.assertEqual(meta["Stadium"], "エディオンピースウイング広島")

    @patch("requests.get")
    def test_save_raw_data(self, mock_get: MagicMock) -> None:
        """save_raw_dataによるファイル出力の整合性を検証."""
        # fetch_comments, fetch_player_detail_stats, fetch_game_meta の順で呼び出される
        resp_comments = MagicMock()
        resp_comments.status_code = 200
        resp_comments.json.return_value = SAMPLE_COMMENTS_DATA

        resp_players = MagicMock()
        resp_players.status_code = 200
        resp_players.json.return_value = SAMPLE_PLAYER_STATS_DATA

        resp_meta = MagicMock()
        resp_meta.status_code = 200
        resp_meta.json.return_value = SAMPLE_META_DATA

        mock_get.side_effect = [resp_comments, resp_players, resp_meta]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.scraper.save_raw_data(
                "2025050301",
                output_dir=tmpdir,
            )

            comments_path = result["comments_path"]
            stats_path = result["stats_path"]
            meta_path = result["meta_path"]

            self.assertTrue(os.path.exists(comments_path))
            self.assertTrue(os.path.exists(stats_path))
            self.assertTrue(os.path.exists(meta_path))

            with open(comments_path, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                self.assertEqual(c_data["game_id"], "2025050301")
                self.assertEqual(c_data["count"], 3)

            with open(stats_path, "r", encoding="utf-8") as f:
                s_data = json.load(f)
                self.assertEqual(s_data["count"], 2)
                self.assertEqual(s_data["player_stats"][0]["Name"], "満田 誠")

    @patch("requests.get")
    def test_api_error_handling(self, mock_get: MagicMock) -> None:
        """APIリクエスト失敗時に例外でクラッシュせず空データを返すことを検証."""
        import requests
        mock_get.side_effect = requests.RequestException("Connection error")

        res_comments = self.scraper.fetch_comments("9999999999")
        self.assertEqual(res_comments, [])

        res_players = self.scraper.fetch_player_detail_stats("9999999999")
        self.assertEqual(res_players, [])

        res_meta = self.scraper.fetch_game_meta("9999999999")
        self.assertEqual(res_meta, {})


if __name__ == "__main__":
    unittest.main()
