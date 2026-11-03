"""
Unit and integration tests for FastAPI Mobile Backend APIs.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from starlette.testclient import TestClient

import pipeline.db as db_module
from api.main import app
from pipeline.db import init_db, get_db_connection


class TestApiMobile(unittest.TestCase):
    """Test suite for mobile REST APIs."""

    def setUp(self) -> None:
        """Create isolated temporary database and upload directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_football.db")
        self.test_upload_dir = Path(self.temp_dir) / "uploads" / "photos"
        self.test_upload_dir.mkdir(parents=True, exist_ok=True)

        # Patch DB path and Upload directory
        self.db_patcher = patch.object(db_module, "DEFAULT_DB_PATH", self.test_db_path)
        self.db_patcher.start()

        import api.routes.notes_photos as np_module
        self.upload_patcher = patch.object(np_module, "UPLOAD_BASE_DIR", self.test_upload_dir)
        self.upload_patcher.start()

        # Initialize schema
        init_db(self.test_db_path)

        # Seed sample match and player data
        self._seed_test_data()

        self.client = TestClient(app)

    def tearDown(self) -> None:
        """Clean up patches and temporary storage."""
        self.db_patcher.stop()
        self.upload_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _seed_test_data(self) -> None:
        """Insert mock match and player stats for testing context."""
        conn = get_db_connection(self.test_db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO matches (
                match_id, season, matchweek, date, home_team_id, away_team_id,
                home_score, away_score, stadium, weather
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "2026_M01_FCT_ZEL",
                2026,
                1,
                "2026-02-23",
                "FCT",
                "ZEL",
                2,
                1,
                "味の素スタジアム",
                "晴",
            ),
        )
        cur.execute(
            """
            INSERT INTO player_match_stats (
                match_id, player_id, player_name, team_id, is_starter,
                minutes_played, position, number, avg_x, avg_y
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "2026_M01_FCT_ZEL",
                "P_FCT_01",
                "小泉 慶",
                "FCT",
                1,
                90,
                "DMF",
                37,
                48.5,
                52.0,
            ),
        )
        cur.execute(
            """
            INSERT INTO player_match_stats (
                match_id, player_id, player_name, team_id, is_starter,
                minutes_played, position, number, avg_x, avg_y
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "2026_M01_FCT_ZEL",
                "P_FCT_02",
                "長倉 幹樹",
                "FCT",
                0,
                20,
                "FW",
                26,
                65.0,
                22.0,
            ),
        )
        conn.commit()
        conn.close()

    def test_health_check(self) -> None:
        """Verify health check endpoint returns 200 and healthy status."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "healthy")

    def test_get_app_context_success(self) -> None:
        """Verify match app context bundle retrieval."""
        resp = self.client.get("/api/matches/2026_M01_FCT_ZEL/app_context")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["match_id"], "2026_M01_FCT_ZEL")
        self.assertEqual(data["home_team"]["team_id"], "FCT")
        self.assertEqual(len(data["home_team"]["starters"]), 1)
        self.assertEqual(data["home_team"]["starters"][0]["player_name"], "小泉 慶")
        self.assertEqual(len(data["home_team"]["bench"]), 1)
        self.assertEqual(data["home_team"]["bench"][0]["player_name"], "長倉 幹樹")
        self.assertEqual(data["status"], "FINISHED")

    def test_get_app_context_not_found(self) -> None:
        """Verify 404 for non-existent match."""
        resp = self.client.get("/api/matches/NON_EXISTENT_MATCH/app_context")
        self.assertEqual(resp.status_code, 404)

    def test_sync_user_actions_and_summary(self) -> None:
        """Test syncing good/bad actions and retrieving summary aggregation."""
        actions_payload = {
            "actions": [
                {
                    "id": "act_001",
                    "match_id": "2026_M01_FCT_ZEL",
                    "player_id": "P_FCT_01",
                    "team_id": "FCT",
                    "action_type": "good",
                    "match_minute": 15,
                    "play_category": "duel",
                    "note": "ナイスボール奪取",
                },
                {
                    "id": "act_002",
                    "match_id": "2026_M01_FCT_ZEL",
                    "player_id": "P_FCT_01",
                    "team_id": "FCT",
                    "action_type": "good",
                    "match_minute": 32,
                    "play_category": "pass",
                    "note": "鋭い縦パス",
                },
                {
                    "id": "act_003",
                    "match_id": "2026_M01_FCT_ZEL",
                    "player_id": "P_FCT_02",
                    "team_id": "FCT",
                    "action_type": "bad",
                    "match_minute": 75,
                    "play_category": "shot",
                    "note": "決定機枠外",
                },
            ]
        }
        # 1. Sync actions
        sync_resp = self.client.post("/api/sync/actions", json=actions_payload)
        self.assertEqual(sync_resp.status_code, 200)
        self.assertEqual(sync_resp.json()["synced_count"], 3)

        # 2. Get summary
        sum_resp = self.client.get("/api/matches/2026_M01_FCT_ZEL/actions/summary")
        self.assertEqual(sum_resp.status_code, 200)
        sum_data = sum_resp.json()
        self.assertEqual(sum_data["total_good"], 2)
        self.assertEqual(sum_data["total_bad"], 1)

        players = {p["player_id"]: p for p in sum_data["players"]}
        self.assertIn("P_FCT_01", players)
        self.assertEqual(players["P_FCT_01"]["good_count"], 2)
        self.assertEqual(players["P_FCT_01"]["net_score"], 2)

        self.assertIn("P_FCT_02", players)
        self.assertEqual(players["P_FCT_02"]["bad_count"], 1)
        self.assertEqual(players["P_FCT_02"]["net_score"], -1)

        # 3. Test Upsert (Update note for act_001)
        update_payload = {
            "actions": [
                {
                    "id": "act_001",
                    "match_id": "2026_M01_FCT_ZEL",
                    "player_id": "P_FCT_01",
                    "team_id": "FCT",
                    "action_type": "good",
                    "match_minute": 15,
                    "play_category": "duel",
                    "note": "修正: 素晴らしいインターセプト",
                }
            ]
        }
        up_resp = self.client.post("/api/sync/actions", json=update_payload)
        self.assertEqual(up_resp.status_code, 200)
        self.assertEqual(up_resp.json()["synced_count"], 1)

        # Total count should still be 3
        sum_resp2 = self.client.get("/api/matches/2026_M01_FCT_ZEL/actions/summary")
        self.assertEqual(sum_resp2.json()["total_good"], 2)

    def test_sync_user_notes(self) -> None:
        """Test syncing observation notes for different match phases."""
        notes_payload = {
            "notes": [
                {
                    "match_id": "2026_M01_FCT_ZEL",
                    "phase": "pre_match",
                    "note": "スタジアム満員、前線プレスに期待。",
                    "mom_player_id": None,
                },
                {
                    "match_id": "2026_M01_FCT_ZEL",
                    "phase": "half_time",
                    "note": "前半1-0でリード。中盤の強度が勝っている。",
                    "mom_player_id": "P_FCT_01",
                },
            ]
        }
        # 1. Sync
        resp = self.client.post("/api/sync/notes", json=notes_payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["synced_count"], 2)

        # 2. Get notes
        get_resp = self.client.get("/api/matches/2026_M01_FCT_ZEL/notes")
        self.assertEqual(get_resp.status_code, 200)
        notes = get_resp.json()["notes"]
        self.assertEqual(len(notes), 2)
        phases = {n["phase"]: n["note"] for n in notes}
        self.assertIn("pre_match", phases)
        self.assertIn("half_time", phases)

        # 3. Update existing phase note
        update_notes = {
            "notes": [
                {
                    "match_id": "2026_M01_FCT_ZEL",
                    "phase": "half_time",
                    "note": "追記: 後半の運動量維持がカギ。",
                    "mom_player_id": "P_FCT_01",
                }
            ]
        }
        self.client.post("/api/sync/notes", json=update_notes)
        get_resp2 = self.client.get("/api/matches/2026_M01_FCT_ZEL/notes")
        notes2 = get_resp2.json()["notes"]
        self.assertEqual(len(notes2), 2)  # Still 2 records (upserted)
        ht_note = next(n for n in notes2 if n["phase"] == "half_time")
        self.assertEqual(ht_note["note"], "追記: 後半の運動量維持がカギ。")

    def test_upload_photo_and_query(self) -> None:
        """Test uploading photo and retrieving by match and stadium."""
        fake_image_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb"
        files = {
            "file": ("stadium_view.jpg", io.BytesIO(fake_image_bytes), "image/jpeg"),
        }
        data = {
            "match_id": "2026_M01_FCT_ZEL",
            "stadium_id": "味の素スタジアム",
            "phase": "pre_match",
            "caption": "快晴のピッチ！",
            "photo_id": "photo_test_123",
        }

        # 1. Upload
        upload_resp = self.client.post("/api/sync/photos", files=files, data=data)
        self.assertEqual(upload_resp.status_code, 200)
        u_json = upload_resp.json()
        self.assertTrue(u_json["success"])
        self.assertEqual(u_json["photo"]["id"], "photo_test_123")
        self.assertIn("/uploads/photos/", u_json["photo"]["file_url"])

        # 2. Query by match
        m_resp = self.client.get("/api/matches/2026_M01_FCT_ZEL/photos")
        self.assertEqual(m_resp.status_code, 200)
        m_items = m_resp.json()["items"]
        self.assertEqual(len(m_items), 1)
        self.assertEqual(m_items[0]["caption"], "快晴のピッチ！")

        # 3. Query by stadium
        s_resp = self.client.get("/api/stadiums/味の素スタジアム/photos")
        self.assertEqual(s_resp.status_code, 200)
        s_items = s_resp.json()["items"]
        self.assertEqual(len(s_items), 1)
        self.assertEqual(s_items[0]["stadium_id"], "味の素スタジアム")

    def test_formation_pattern_coordinates(self) -> None:
        """Verify detailed tactical formation positions map to proper pitch coordinates."""
        from api.routes.context import _auto_layout_starters
        from api.schemas import PlayerContextItem

        # 1. Test 3-back pattern
        starters_3back = [
            PlayerContextItem(player_id="1", player_name="GK", number=1, position="GK", is_starter=True),
            PlayerContextItem(player_id="2", player_name="LCB", number=2, position="LCB", is_starter=True),
            PlayerContextItem(player_id="3", player_name="CB", number=3, position="CB", is_starter=True),
            PlayerContextItem(player_id="4", player_name="RCB", number=4, position="RCB", is_starter=True),
            PlayerContextItem(player_id="5", player_name="LWB", number=5, position="LWB", is_starter=True),
            PlayerContextItem(player_id="6", player_name="RWB", number=6, position="RWB", is_starter=True),
            PlayerContextItem(player_id="7", player_name="CF", number=7, position="CF", is_starter=True),
        ]
        layout_3b = _auto_layout_starters(starters_3back)
        coord_map_3b = {p.position: (p.pitch_x, p.pitch_y) for p in layout_3b}

        self.assertEqual(coord_map_3b["GK"], (50.0, 90.0))
        self.assertEqual(coord_map_3b["LCB"], (24.0, 72.0))
        self.assertEqual(coord_map_3b["CB"], (50.0, 70.0))
        self.assertEqual(coord_map_3b["RCB"], (76.0, 72.0))
        self.assertEqual(coord_map_3b["LWB"], (12.0, 52.0))
        self.assertEqual(coord_map_3b["CF"], (50.0, 16.0))

        # 2. Test 4-back pattern
        starters_4back = [
            PlayerContextItem(player_id="10", player_name="GK", number=1, position="GK", is_starter=True),
            PlayerContextItem(player_id="11", player_name="LSB", number=2, position="LSB", is_starter=True),
            PlayerContextItem(player_id="12", player_name="LCB", number=3, position="LCB", is_starter=True),
            PlayerContextItem(player_id="13", player_name="RCB", number=4, position="RCB", is_starter=True),
            PlayerContextItem(player_id="14", player_name="RSB", number=5, position="RSB", is_starter=True),
            PlayerContextItem(player_id="15", player_name="LCF", number=6, position="LCF", is_starter=True),
            PlayerContextItem(player_id="16", player_name="RCF", number=7, position="RCF", is_starter=True),
        ]
        layout_4b = _auto_layout_starters(starters_4back)
        coord_map_4b = {p.position: (p.pitch_x, p.pitch_y) for p in layout_4b}

        self.assertEqual(coord_map_4b["LSB"], (14.0, 72.0))
        self.assertEqual(coord_map_4b["LCB"], (38.0, 72.0))
        self.assertEqual(coord_map_4b["RCB"], (62.0, 72.0))
        self.assertEqual(coord_map_4b["RSB"], (86.0, 72.0))
        self.assertEqual(coord_map_4b["LCF"], (35.0, 18.0))
        self.assertEqual(coord_map_4b["RCF"], (65.0, 18.0))


if __name__ == "__main__":
    unittest.main()
