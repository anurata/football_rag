"""Unit tests for scripts/cleanup_mock_and_enrich_metrics.py."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.cleanup_mock_and_enrich_metrics import (
    clean_name_key,
    normalize_yahoo_coord,
    parse_yahoo_match_positions,
    compute_player_xg_xa_weights,
    distribute_team_metrics,
    purge_mock_matches,
)


class TestCleanupAndEnrichMetrics(unittest.TestCase):
    """Test suite for mock cleanup and player metrics enrichment."""

    def test_clean_name_key(self) -> None:
        """Verify normalization of player names."""
        self.assertEqual(clean_name_key("キム スンギュ"), "キムスンギュ")
        self.assertEqual(clean_name_key("田中　颯"), "田中颯")
        self.assertEqual(clean_name_key("マテウス・サヴィオ"), "マテウスサヴィオ")

    def test_normalize_yahoo_coord(self) -> None:
        """Verify coordinate scaling to 0..100 range."""
        # Own goal center
        nx, ny = normalize_yahoo_coord(-150, 0)
        self.assertEqual(nx, 0.0)
        self.assertEqual(ny, 50.0)

        # Center pitch
        cx, cy = normalize_yahoo_coord(0, 0)
        self.assertEqual(cx, 50.0)
        self.assertEqual(cy, 50.0)

        # Opponent goal center
        ox, oy = normalize_yahoo_coord(150, 0)
        self.assertEqual(ox, 100.0)
        self.assertEqual(oy, 50.0)

    def test_parse_yahoo_match_positions(self) -> None:
        """Verify parsing positions from Yahoo JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_json = {
                "formation_snapshots": [
                    {
                        "home_players": [
                            {"player_name": "選手A", "x": -150, "y": 0},
                            {"player_name": "選手B", "x": 0, "y": 50},
                        ],
                        "away_players": [],
                    },
                    {
                        "home_players": [
                            {"player_name": "選手A", "x": -140, "y": 0},
                            {"player_name": "選手B", "x": 20, "y": 50},
                        ],
                        "away_players": [],
                    },
                ],
            }
            summary_path = Path(tmpdir) / "test_match_summary.json"
            summary_path.write_text(json.dumps(sample_json, ensure_ascii=False), encoding="utf-8")

            coords = parse_yahoo_match_positions(summary_path)
            self.assertIn("選手A", coords)
            self.assertIn("選手B", coords)
            # 選手A avg x = -145 -> ( -145 + 150 ) / 3 = 1.7
            self.assertEqual(coords["選手A"][0], 1.7)
            self.assertEqual(coords["選手A"][1], 50.0)

    def test_distribute_team_metrics(self) -> None:
        """Verify distributed xG and xA calculations."""
        mock_players = [
            {
                "goals": 1,
                "assists": 0,
                "raw_stats_json": json.dumps({
                    "yahoo": {"shoots": 3, "shoots_on_target": 2},
                    "cbp": {"shoot": 1.2},
                }),
            },
            {
                "goals": 0,
                "assists": 1,
                "raw_stats_json": json.dumps({
                    "yahoo": {"shoots": 0, "shoots_on_target": 0, "through_passes": 2},
                    "cbp": {"pass": 2.5},
                }),
            },
        ]

        metrics = distribute_team_metrics(1.50, mock_players)
        self.assertEqual(len(metrics), 2)
        p1_xg, p1_xa = metrics[0]
        p2_xg, p2_xa = metrics[1]

        # Player 1 should have high xG
        self.assertGreater(p1_xg, 0.5)
        # Player 2 should have high xA
        self.assertGreater(p2_xa, 0.3)

    def test_purge_mock_matches(self) -> None:
        """Verify purging mock matches from sqlite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_db = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(test_db)
            cur = conn.cursor()
            cur.execute("CREATE TABLE matches (match_id TEXT PRIMARY KEY)")
            cur.execute("CREATE TABLE player_match_stats (match_id TEXT)")
            cur.execute("CREATE TABLE player_match_positions (match_id TEXT)")
            cur.execute("CREATE TABLE match_formations (match_id TEXT)")
            cur.execute("CREATE TABLE team_match_stats (match_id TEXT)")
            cur.execute("CREATE TABLE match_events (match_id TEXT)")
            cur.execute("CREATE TABLE match_reviews (match_id TEXT)")

            cur.execute("INSERT INTO matches VALUES ('20261101_MOCK')")
            cur.execute("INSERT INTO matches VALUES ('20260808_REAL')")
            cur.execute("INSERT INTO player_match_stats VALUES ('20261101_MOCK')")
            conn.commit()
            conn.close()

            deleted = purge_mock_matches(test_db, pattern="20261101%")
            self.assertEqual(deleted, 2)

            conn = sqlite3.connect(test_db)
            cur = conn.cursor()
            cur.execute("SELECT match_id FROM matches")
            remaining = cur.fetchall()
            conn.close()
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0][0], "20260808_REAL")


if __name__ == "__main__":
    unittest.main()
