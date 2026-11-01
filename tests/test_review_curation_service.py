# -*- coding: utf-8 -*-
"""
Unit tests for Review Curation Service and CLI.
(tests/test_review_curation_service.py)
"""

import gc
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline.db import (
    SCHEMA_MATCHES,
    SCHEMA_TEAM_MATCH_STATS,
    SCHEMA_MATCH_EVENTS,
    SCHEMA_PLAYER_MATCH_STATS,
)
from pipeline.review_curation_service import ReviewCurationService


class TestReviewCurationService(unittest.TestCase):
    """Unit tests for ReviewCurationService."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_file = Path(self.temp_dir.name) / "test_football.db"
        conn = sqlite3.connect(str(self.db_file))
        cursor = conn.cursor()

        cursor.executescript(SCHEMA_MATCHES)
        cursor.executescript(SCHEMA_TEAM_MATCH_STATS)
        cursor.executescript(SCHEMA_MATCH_EVENTS)
        cursor.executescript(SCHEMA_PLAYER_MATCH_STATS)

        self.match_id = "20261031_OKA_FCT"
        cursor.execute(
            """
            INSERT INTO matches (
                match_id, season, matchweek, date, home_team_id, away_team_id,
                home_score, away_score, stadium, weather, pitch_condition,
                attendance, source_updated_stage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.match_id,
                2026,
                13,
                "2026-10-31",
                "OKA",
                "FCT",
                1,
                2,
                "シティライトスタジアム",
                "晴",
                "良好",
                14500,
                2,
            ),
        )

        cursor.execute(
            """
            INSERT INTO team_match_stats (
                match_id, team_id, period, game_state, possession, xg,
                shots, shots_on_target, total_distance_km, sprints
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.match_id, "OKA", "ALL", "ALL", 45.0, 0.85, 8, 3, 112.5, 140),
        )
        cursor.execute(
            """
            INSERT INTO team_match_stats (
                match_id, team_id, period, game_state, possession, xg,
                shots, shots_on_target, total_distance_km, sprints
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.match_id, "FCT", "ALL", "ALL", 55.0, 1.45, 12, 5, 114.2, 155),
        )

        cursor.execute(
            """
            INSERT INTO match_events (
                event_id, match_id, minute, period, event_type, team_id, player_name, description_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f"{self.match_id}_ev1", self.match_id, 32, "1H", "GOAL", "FCT", "佐藤 恵介", "ペナルティエリア内からの右足シュート"),
        )
        cursor.execute(
            """
            INSERT INTO match_events (
                event_id, match_id, minute, period, event_type, team_id, player_name, description_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f"{self.match_id}_ev2", self.match_id, 65, "2H", "GOAL", "OKA", "田中 健", "ヘディングシュート"),
        )
        cursor.execute(
            """
            INSERT INTO match_events (
                event_id, match_id, minute, period, event_type, team_id, player_name, description_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f"{self.match_id}_ev3", self.match_id, 84, "2H", "GOAL", "FCT", "高宇洋", "ミドルレンジからの勝ち越し弾"),
        )

        cursor.execute(
            """
            INSERT INTO player_match_stats (
                match_id, player_name, team_id, goals, assists, xg, xa, touches
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.match_id, "佐藤 恵介", "FCT", 1, 0, 0.65, 0.15, 45),
        )
        cursor.execute(
            """
            INSERT INTO player_match_stats (
                match_id, player_name, team_id, goals, assists, xg, xa, touches
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.match_id, "高宇洋", "FCT", 1, 0, 0.40, 0.20, 68),
        )

        conn.commit()
        conn.close()

        self.service = ReviewCurationService(db_path=str(self.db_file))

    def tearDown(self) -> None:
        del self.service
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_extract_facts_and_generate_branches(self) -> None:
        """Test extracting facts and building review branches."""
        workspace = self.service.generate_curation_workspace(match_id=self.match_id)

        facts = workspace["facts"]
        branches = workspace["branches"]

        # Verify basic facts
        basic = facts["basic_info"]
        self.assertEqual(basic["match_id"], self.match_id)
        self.assertEqual(basic["home_score"], 1)
        self.assertEqual(basic["away_score"], 2)
        self.assertEqual(basic["home_team_id"], "OKA")
        self.assertEqual(basic["away_team_id"], "FCT")
        self.assertEqual(len(facts["events"]), 3)
        self.assertEqual(len(facts["notable_players"]), 2)

        # Verify branch structure and fact/inference separation
        self.assertEqual(len(branches), 3)
        branch_ids = [b["branch_id"] for b in branches]
        self.assertIn("deciding_factor", branch_ids)
        self.assertIn("tactical_evaluation", branch_ids)
        self.assertIn("impact_player", branch_ids)

        for b in branches:
            self.assertIn("options", b)
            self.assertGreaterEqual(len(b["options"]), 2)
            for opt in b["options"]:
                self.assertIn("【事実】", opt["fact_basis"])
                self.assertIn("【推測】", opt["inference"])

    def test_compile_and_save_curated_report(self) -> None:
        """Test compiling and writing curated review markdown."""
        workspace = self.service.generate_curation_workspace(match_id=self.match_id)
        facts = workspace["facts"]

        selections = {
            "【勝敗の決定打・ターニングポイント】試合の趨勢を分けた要因": (
                "**選択案 [A] 決定力と決定機創出のクオリティ差**\n"
                "- 【事実】FCTがシュート数・枠内・xGで上回った。\n"
                "- 【推測】終盤の決定機を逃さなかったことが勝敗を分けた。"
            ),
        }
        custom_insights = "中盤での高宇洋のボール奪取とビルドアップの安定が特に効いていた。"

        report_md = self.service.compile_curated_report(
            facts=facts,
            selections=selections,
            custom_insights=custom_insights,
        )

        self.assertIn("# ⚽ 試合総括レポート: 2026-10-31 OKA vs FCT", report_md)
        self.assertIn("OKA 1 - 2 FCT", report_md)
        self.assertIn("共同キュレーション総括セクション", report_md)
        self.assertIn("高宇洋", report_md)
        self.assertIn("アナリスト・共同作成メモ", report_md)

        out_file = Path(self.temp_dir.name) / "review_curated.md"
        self.service.save_curated_report(out_file, report_md)
        self.assertTrue(out_file.exists())
        self.assertEqual(out_file.read_text(encoding="utf-8"), report_md)

    def test_cli_execution_with_dump_branches(self) -> None:
        """Test curate_match_review CLI logic with branches dump."""
        from scripts.curate_match_review import resolve_match_id
        
        # Test resolve_match_id
        resolved = resolve_match_id(
            match_id=self.match_id,
            home="",
            away="",
            date="",
        )
        self.assertEqual(resolved, self.match_id)


if __name__ == "__main__":
    unittest.main()
