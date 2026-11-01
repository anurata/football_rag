"""Unit tests for scripts/export_team_players_sheet.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import pandas as pd

from scripts.export_team_players_sheet import (
    load_player_json,
    load_player_match_stats,
    build_basic_info_records,
    build_season_stats_records,
    build_career_history_records,
    build_match_summary_records,
    flatten_raw_stats_json,
    export_team_to_excel,
    export_team_to_csvs,
    export_team_player_data,
)


class TestExportTeamPlayersSheet(unittest.TestCase):
    """Test suite for player spreadsheet exports."""

    def test_load_fct_player_json(self) -> None:
        """Verify loading FCT players from data/players/FCT_players.json."""
        players = load_player_json("FCT")
        self.assertIsInstance(players, list)
        self.assertGreater(len(players), 0)
        first_player = players[0]
        self.assertIn("player_id", first_player)
        self.assertIn("name", first_player)
        self.assertEqual(first_player["name"], "田中 颯")

    def test_flatten_raw_stats_json(self) -> None:
        """Verify flattening Football Lab / SPAIA / Yahoo metrics from JSON."""
        sample_json = """
        {
            "rating": 6.5,
            "max_speed_kmh": 32.1,
            "distance_first_half": 5.2,
            "distance_second_half": 5.1,
            "plays_by_area": {
                "total": 80,
                "attacking_third": 25,
                "middle_third": 40,
                "defensive_third": 15
            },
            "discipline": {
                "yellow_cards": 1,
                "red_cards": 0,
                "fouls": 2,
                "suffer_fouls": 1
            },
            "cbp": {
                "attack": 2.1,
                "defense": 1.5,
                "gain": 4.0,
                "pass": 1.8,
                "cross": 0.3,
                "total": 9.7
            },
            "spaia": {
                "pa_entries": 3,
                "pass_count": 45,
                "pass_rate": 82.2,
                "tackle_count": 4,
                "clear_count": 2
            },
            "yahoo": {
                "shoots": 2,
                "shoots_on_target": 1,
                "loose_ball_recoveries": 3
            }
        }
        """
        flat = flatten_raw_stats_json(sample_json)
        self.assertEqual(flat["評点(Rating)"], 6.5)
        self.assertEqual(flat["最高時速(km/h)"], 32.1)
        self.assertEqual(flat["総プレー数"], 80)
        self.assertEqual(flat["イエローカード"], 1)
        self.assertEqual(flat["CBP_総合"], 9.7)
        self.assertEqual(flat["PA進入数"], 3)
        self.assertEqual(flat["SPAIA_パス成功率(%)"], 82.2)
        self.assertEqual(flat["シュート数"], 2)
        self.assertEqual(flat["枠内シュート数"], 1)
        self.assertEqual(flat["こぼれ球奪取"], 3)

    def test_build_records(self) -> None:
        """Verify dictionary to records transformations."""
        mock_player = {
            "player_id": "9999",
            "number": "10",
            "name": "テスト 選手",
            "name_en": "TEST Player",
            "position": "MF",
            "detailed_position_ja": "攻撃的ミッドフィールダー",
            "detailed_position_code": "AM",
            "dominant_foot": "右足",
            "birthdate": "2000/01/01",
            "height_cm": "178",
            "weight_kg": "70",
            "birthplace": "東京都",
            "nationalities": ["Japan"],
            "previous_club": "FCテスト",
            "joined_date": "2024/01/01",
            "contract_until": "2027/01/31",
            "market_value_eur": 500000,
            "loan_from_club": None,
            "loan_until": None,
            "matches": "15",
            "goals": "3",
            "national_team_caps": "0",
            "jleague_debut": "2024/02/23",
            "jleague_first_goal": "2024/03/10",
            "strong_points": ["高精度パス", "推進力"],
            "tm_player_id": "123456",
            "photo_url": "http://example.com/test.png",
            "season_stats": {
                "ゴール期待値": 2.45,
                "枠内シュート率": "45.0%",
            },
            "career_history": [
                {
                    "season": "2024",
                    "club": "FC東京",
                    "league": "J1",
                    "league_matches": "15",
                    "league_goals": "3",
                },
            ],
        }

        # 1. Basic info
        basic = build_basic_info_records([mock_player])
        self.assertEqual(len(basic), 1)
        self.assertEqual(basic[0]["氏名"], "テスト 選手")
        self.assertEqual(basic[0]["スカウティング特徴・強み"], "高精度パス / 推進力")

        # 2. Season stats
        season = build_season_stats_records([mock_player])
        self.assertEqual(len(season), 1)
        self.assertEqual(season[0]["ゴール期待値"], 2.45)

        # 3. Career history
        career = build_career_history_records([mock_player])
        self.assertEqual(len(career), 1)
        self.assertEqual(career[0]["年度"], "2024")

        # 4. Match summary with expanded schema
        mock_stats = [
            {
                "選手名": "テスト 選手",
                "先発区分": "先発",
                "出場時間(分)": 90,
                "得点": 1,
                "アシスト": 0,
                "ゴール期待値(xG)": 0.4,
                "アシスト期待値(xA)": 0.1,
                "走行距離(km)": 10.5,
                "スプリント回数": 18,
                "総合CBP点": 12.5,
                "デュエル勝利数": 5,
                "評点(Rating)": 7.0,
                "最高時速(km/h)": 32.5,
                "シュート数": 3,
                "枠内シュート数": 2,
                "PA進入数": 4,
                "タックル数": 2,
                "クリア数": 1,
                "こぼれ球奪取": 5,
                "SPAIA_パス成功率(%)": 85.0,
            },
        ]
        summary = build_match_summary_records([mock_player], mock_stats)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["DB記録試合数"], 1)
        self.assertEqual(summary[0]["先発回数"], 1)
        self.assertEqual(summary[0]["ゴール"], 1)
        self.assertEqual(summary[0]["平均評点"], 7.0)
        self.assertEqual(summary[0]["総シュート数"], 3)
        self.assertEqual(summary[0]["総PA進入数"], 4)
        self.assertEqual(summary[0]["最高時速(km/h)"], 32.5)

    def test_export_excel_and_csv_generation(self) -> None:
        """Verify excel and csv export to temporary directory."""
        players = load_player_json("FCT")
        match_stats = load_player_match_stats("FCT")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            excel_file = tmp_path / "test_FCT.xlsx"

            # Test Excel export
            export_team_to_excel("FCT", excel_file, players, match_stats)
            self.assertTrue(excel_file.exists())

            with pd.ExcelFile(excel_file) as xls:
                self.assertIn("1_基本情報・契約", xls.sheet_names)
                self.assertIn("2_実戦スタッツ集計(DB)", xls.sheet_names)
                self.assertIn("3_公式詳細スタッツ", xls.sheet_names)
                self.assertIn("4_年度別キャリア履歴", xls.sheet_names)
                self.assertIn("5_試合別詳細生ログ(DB)", xls.sheet_names)

                df_logs = pd.read_excel(xls, sheet_name="5_試合別詳細生ログ(DB)")
                self.assertIn("PA進入数", df_logs.columns)
                self.assertIn("CBP_総合", df_logs.columns)
                self.assertIn("最高時速(km/h)", df_logs.columns)

            # Test CSV export
            csv_paths = export_team_to_csvs("FCT", tmp_path, players, match_stats)
            self.assertGreaterEqual(len(csv_paths), 4)
            for p in csv_paths:
                self.assertTrue(p.exists())

    def test_export_team_player_data_fct(self) -> None:
        """Verify execution of full export for FCT."""
        result = export_team_player_data("FCT")
        self.assertEqual(result["team_id"], "FCT")
        self.assertGreater(result["player_count"], 0)
        self.assertTrue(Path(result["excel_path"]).exists())
        for cp in result["csv_paths"]:
            self.assertTrue(Path(cp).exists())


if __name__ == "__main__":
    unittest.main()
