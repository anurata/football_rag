# -*- coding: utf-8 -*-
"""Unit tests for pipeline/flab_team_stats_ingester.py."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline.flab_team_stats_ingester import (
    ingest_all_flab_team_stats,
    parse_flab_team_side,
    safe_float,
    safe_int,
)


class TestFlabTeamStatsIngester(unittest.TestCase):
    """Test Football LAB team stats ingestion and metric parsing."""

    def test_safe_converters(self) -> None:
        """Test numeric conversion for various Football LAB string formats."""
        self.assertEqual(safe_float("26.1%"), 26.1)
        self.assertEqual(safe_float("(14.78)"), 14.78)
        self.assertEqual(safe_float("1,778"), 1778.0)
        self.assertIsNone(safe_float("-"))
        self.assertIsNone(safe_float(""))
        self.assertIsNone(safe_float(None))

        self.assertEqual(safe_int("116,883m"), 116883)
        self.assertEqual(safe_int("23"), 23)
        self.assertEqual(safe_int("5.0"), 5)
        self.assertIsNone(safe_int("-"))

    def test_parse_flab_team_side(self) -> None:
        """Test extraction of home and away metrics from raw stats structure."""
        stats_list = [
            {
                "name": "ゴール期待値",
                "home_val": "2.296",
                "home_rate": "-",
                "home_avg": "1.778",
                "away_val": "0.649",
                "away_rate": "-",
                "away_avg": "0.989",
            },
            {
                "name": "インターセプト",
                "home_val": "2",
                "home_rate": "-",
                "home_avg": "1.8",
                "away_val": "0",
                "away_rate": "-",
                "away_avg": "1.3",
            },
            {
                "name": "ＣＫ",
                "home_val": "7",
                "home_rate": "-",
                "home_avg": "5.3",
                "away_val": "5",
                "away_rate": "-",
                "away_avg": "4.1",
            },
            {
                "name": "クロス",
                "home_val": "14",
                "home_rate": "(42.9%)",
                "home_avg": "15.3",
                "away_val": "8",
                "away_rate": "(25.0%)",
                "away_avg": "9.9",
            },
        ]
        cbp_dict = {
            "team": [
                {
                    "name": "攻撃",
                    "home_val": "21.25",
                    "home_avg": "19.01",
                    "away_val": "9.21",
                    "away_avg": "10.99",
                },
                {
                    "name": "奪取",
                    "home_val": "99.54",
                    "home_avg": "91.10",
                    "away_val": "91.92",
                    "away_avg": "73.83",
                },
            ],
        }

        # Home
        h = parse_flab_team_side(
            match_id="20261025_FCT_MIT",
            team_id="FCT",
            is_home=True,
            opponent_team_id="MIT",
            stats_list=stats_list,
            cbp_dict=cbp_dict,
        )
        self.assertEqual(h["intercepts"], 2)
        self.assertEqual(h["corner_kicks"], 7)
        self.assertEqual(h["crosses"], 14)
        self.assertEqual(h["crosses_rate"], 42.9)
        self.assertEqual(h["cbp_gain"], 99.54)
        self.assertEqual(h["cbp_gain_avg"], 91.10)

        # Away
        a = parse_flab_team_side(
            match_id="20261025_FCT_MIT",
            team_id="MIT",
            is_home=False,
            opponent_team_id="FCT",
            stats_list=stats_list,
            cbp_dict=cbp_dict,
        )
        self.assertEqual(a["intercepts"], 0)
        self.assertEqual(a["corner_kicks"], 5)
        self.assertEqual(a["crosses"], 8)
        self.assertEqual(a["crosses_rate"], 25.0)
        self.assertEqual(a["cbp_gain"], 91.92)
        self.assertEqual(a["cbp_gain_avg"], 73.83)

    def test_ingest_into_sqlite(self) -> None:
        """Test full ingestion flow with in-memory/temp sqlite DB."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / "test.db"
            raw_dir = tmp_path / "raw"
            raw_dir.mkdir()

            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE matches (
                    match_id TEXT PRIMARY KEY,
                    season INTEGER,
                    matchweek INTEGER,
                    date TEXT,
                    home_team_id TEXT,
                    away_team_id TEXT
                );
                """,
            )
            conn.execute(
                """
                INSERT INTO matches VALUES ('20261025_FCT_MIT', 2026, 12, '2026-10-25', 'FCT', 'MIT');
                """,
            )
            conn.commit()
            conn.close()

            # Create mock raw json
            raw_data = {
                "match_id": "20261025_FCT_MIT",
                "date": "2026-10-25",
                "home_team_id": "FCT",
                "away_team_id": "MIT",
                "data": {
                    "stats": [
                        {
                            "name": "インターセプト",
                            "home_val": "2",
                            "home_rate": "-",
                            "home_avg": "1.8",
                            "away_val": "0",
                            "away_rate": "-",
                            "away_avg": "1.3",
                        },
                        {
                            "name": "ＣＫ",
                            "home_val": "7",
                            "home_rate": "-",
                            "home_avg": "5.3",
                            "away_val": "5",
                            "away_rate": "-",
                            "away_avg": "4.1",
                        },
                    ],
                    "cbp": {"team": []},
                },
            }
            (raw_dir / "20261025_FCT_MIT.json").write_text(
                json.dumps(raw_data, ensure_ascii=False),
                encoding="utf-8",
            )

            res = ingest_all_flab_team_stats(db_path=db_path, flab_dir=raw_dir)
            self.assertEqual(res["total_records"], 2)
            self.assertEqual(res["total_matches"], 1)

            # Query and verify
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT team_id, intercepts, corner_kicks FROM team_match_flab_stats ORDER BY team_id",
            ).fetchall()
            conn.close()

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], ("FCT", 2, 7))
            self.assertEqual(rows[1], ("MIT", 0, 5))


if __name__ == "__main__":
    unittest.main()
