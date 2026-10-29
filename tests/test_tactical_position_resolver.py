"""Unit tests for TacticalPositionResolver (tests/test_tactical_position_resolver.py)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline.tactical_position_resolver import TacticalPositionResolver


class TestTacticalPositionResolver(unittest.TestCase):
    """TacticalPositionResolver のマルチソース合議・時間帯スティント検証."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        self.db_path = self.base / "test.db"
        self.yahoo_dir = self.base / "yahoo"
        self.spaia_dir = self.base / "spaia"
        self.md_dir = self.base / "md"
        self.yahoo_dir.mkdir()
        self.spaia_dir.mkdir()
        self.md_dir.mkdir()

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE entity_master_players (
                player_id TEXT PRIMARY KEY,
                team_id TEXT,
                number INTEGER,
                canonical_name TEXT
            )
            """,
        )
        cur.execute(
            """
            CREATE TABLE matches (
                match_id TEXT PRIMARY KEY,
                season INTEGER,
                date TEXT,
                home_team_id TEXT,
                away_team_id TEXT
            )
            """,
        )
        cur.executemany(
            "INSERT INTO entity_master_players VALUES (?, ?, ?, ?)",
            [
                ("P_FCT_10", "FCT", 10, "佐藤 恵允"),
                ("P_FCT_4", "FCT", 4, "稲村 隼翔"),
                ("P_MIT_25", "MIT", 25, "真瀬 拓海"),
            ],
        )
        cur.execute(
            "INSERT INTO matches VALUES ('20261025_FCT_MIT', 2026, '2026-10-25', 'FCT', 'MIT')",
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_role_shift_text_override_and_spaia_fluidity(self) -> None:
        """時間帯コンバート(RSH->LSB)、記述による図誤り補正(LSB->LCB)、SPAIA両サイド検知を総合検証."""
        summary_payload = {
            "game_id": "2026102505",
            "lineup": {
                "home": {
                    "starters": [
                        {"registered_pos": "DF", "number": "4", "player_name": "稲村 隼翔", "sub_info": ""},
                        {"registered_pos": "MF", "number": "10", "player_name": "佐藤 恵允", "sub_info": ""},
                    ],
                    "bench": [],
                },
                "away": {
                    "starters": [
                        {"registered_pos": "DF", "number": "25", "player_name": "真瀬 拓海", "sub_info": ""},
                    ],
                    "bench": [],
                },
            },
            "formation_snapshots": [
                {
                    "snapshot_index": 0,
                    "time_label": "前半0分",
                    "minute_approx": 0,
                    "home_formation": "4-4-2",
                    "away_formation": "3-4-2-1",
                    "home_players": [
                        # 仮にYahoo図が誤って稲村をLSBとしたケース
                        {
                            "number": "4",
                            "player_name": "稲村 隼翔",
                            "registered_pos": "DF",
                            "inferred_role": "LSB",
                            "role_group": "FB",
                            "inferred_lane": "LEFT",
                        },
                        {
                            "number": "10",
                            "player_name": "佐藤 恵允",
                            "registered_pos": "MF",
                            "inferred_role": "RSH",
                            "role_group": "WIDE_ATT",
                            "inferred_lane": "RIGHT",
                        },
                    ],
                    "away_players": [
                        {
                            "number": "25",
                            "player_name": "真瀬 拓海",
                            "registered_pos": "DF",
                            "inferred_role": "RWB",
                            "role_group": "WB",
                            "inferred_lane": "RIGHT",
                        },
                    ],
                },
                {
                    "snapshot_index": 1,
                    "time_label": "後半15分",
                    "minute_approx": 60,
                    "home_formation": "4-4-2",
                    "away_formation": "3-4-2-1",
                    "home_players": [
                        {
                            "number": "4",
                            "player_name": "稲村 隼翔",
                            "registered_pos": "DF",
                            "inferred_role": "LSB",
                            "role_group": "FB",
                            "inferred_lane": "LEFT",
                        },
                        # 後半15分から佐藤恵允が RSB に下がったケース
                        {
                            "number": "10",
                            "player_name": "佐藤 恵允",
                            "registered_pos": "MF",
                            "inferred_role": "RSB",
                            "role_group": "FB",
                            "inferred_lane": "RIGHT",
                        },
                    ],
                    "away_players": [
                        {
                            "number": "25",
                            "player_name": "真瀬 拓海",
                            "registered_pos": "DF",
                            "inferred_role": "RWB",
                            "role_group": "WB",
                            "inferred_lane": "RIGHT",
                        },
                    ],
                },
            ],
        }
        (self.yahoo_dir / "20261025_FCT_MIT_summary.json").write_text(
            json.dumps(summary_payload, ensure_ascii=False),
            encoding="utf-8",
        )

        # 公式戦評MDで「稲村 隼翔は左CBとして...」かつ「稲村からのパスを受けた右SBの石原」を含む文を配置
        (self.md_dir / "20261025_FCT_MIT.md").write_text(
            "稲村 隼翔からのパスを受けた右SBの石原がクロスを送る。稲村 隼翔は左CBとして最終ラインから高精度のフィードを供給した。",
            encoding="utf-8",
        )

        # SPAIAで佐藤恵允が左右PA脇(L=4, R=5)で両方プレーしていたケース
        (self.spaia_dir / "2026102505_player_stats.json").write_text(
            json.dumps(
                {
                    "player_stats": [
                        {"Name": "佐藤　恵允", "PASidePlayLCount": "4", "PASidePlayRCount": "5"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        resolver = TacticalPositionResolver(
            db_path=self.db_path,
            yahoo_dir=self.yahoo_dir,
            spaia_dir=self.spaia_dir,
            md_dir=self.md_dir,
        )
        res = resolver.resolve_all_2026_matches()
        self.assertEqual(res["matches_resolved"], 1)
        self.assertEqual(res["total_player_positions"], 3)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = {
            r["player_id"]: dict(r)
            for r in conn.execute("SELECT * FROM player_match_positions").fetchall()
        }
        conn.close()

        # 1. 稲村は記述オーバーライドにより LCB / CB / TEXT_CORRECTED に補正されていること
        inamura = rows["P_FCT_4"]
        self.assertEqual(inamura["primary_role"], "LCB")
        self.assertEqual(inamura["primary_role_group"], "CB")
        self.assertEqual(inamura["confidence"], "TEXT_CORRECTED")

        # 2. 佐藤恵允は 0-60分 RSH / 60-90分 RSB の2区間スティントと ROLE_SHIFTED + BOTH_FLANKS を持つこと
        sato = rows["P_FCT_10"]
        stints = json.loads(sato["role_stints_json"])
        tags = json.loads(sato["fluidity_tags_json"])
        self.assertEqual(len(stints), 2)
        self.assertEqual(stints[0]["role"], "RSH")
        self.assertEqual(stints[1]["role"], "RSB")
        self.assertIn("ROLE_SHIFTED", tags)
        self.assertIn("BOTH_FLANKS", tags)


if __name__ == "__main__":
    unittest.main()
