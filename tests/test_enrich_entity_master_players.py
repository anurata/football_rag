"""
tests/test_enrich_entity_master_players.py

Unit tests for experiments/enrich_entity_master_players.py
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from experiments.enrich_entity_master_players import (
    build_player_aliases,
    clean_name_key,
    ensure_schema,
    load_dominant_foot_map,
    make_player_id,
    parse_player_record,
    resolve_dominant_foot,
    run_enrichment,
    safe_int_conversion,
    upsert_player_records,
)


class TestEnrichEntityMasterPlayers(unittest.TestCase):
    """Test suite for player master enrichment."""

    def test_clean_name_key(self) -> None:
        self.assertEqual(clean_name_key("長友 佑都"), "長友佑都")
        self.assertEqual(clean_name_key("マルセロ・ヒアン"), "マルセロヒアン")
        self.assertEqual(clean_name_key("ディエゴ　オリヴェイラ"), "ディエゴオリヴェイラ")
        self.assertEqual(clean_name_key(""), "")

    def test_make_player_id(self) -> None:
        pid = make_player_id("FCT", 2, "室屋 成")
        self.assertEqual(pid, "P_FCT_2_室屋成")

        long_name_pid = make_player_id("FCT", 6, "バングーナガンデ 佳史扶")
        self.assertEqual(long_name_pid, "P_FCT_6_バングーナガンデ")

    def test_safe_int_conversion(self) -> None:
        self.assertEqual(safe_int_conversion("176"), 176)
        self.assertEqual(safe_int_conversion("176cm"), 176)
        self.assertEqual(safe_int_conversion(70), 70)
        self.assertIsNone(safe_int_conversion("-"))
        self.assertEqual(safe_int_conversion(None, 0), 0)

    def test_resolve_dominant_foot(self) -> None:
        dominant_map = {"室屋 成": "右足", "バングーナガンデ佳史扶": "左足"}
        self.assertEqual(
            resolve_dominant_foot("室屋 成", None, dominant_map),
            "右足",
        )
        self.assertEqual(
            resolve_dominant_foot("バングーナガンデ 佳史扶", None, dominant_map),
            "左足",
        )
        self.assertEqual(
            resolve_dominant_foot("未知 選手", "右足", dominant_map),
            "右足",
        )
        self.assertIsNone(
            resolve_dominant_foot("未知 選手", "", dominant_map),
        )

    def test_build_player_aliases(self) -> None:
        aliases = build_player_aliases("室屋 成", "MUROYA Sei", "室屋成")
        self.assertIn("室屋 成", aliases)
        self.assertIn("室屋成", aliases)
        self.assertIn("室屋　成", aliases)
        self.assertIn("MUROYA Sei", aliases)

    def test_parse_player_record(self) -> None:
        raw_player: Dict[str, Any] = {
            "player_id": "1632225",
            "team_id": "KAS",
            "name": "早川 友基",
            "name_en": "HAYAKAWA Tomoki",
            "club_name": "鹿島アントラーズ",
            "position": "GK",
            "number": "1",
            "dominant_foot": "右足",
            "photo_url": "https://example.com/p.webp",
            "thumbnail_url": "",
            "birthplace": "神奈川県",
            "birthdate": "1999/3/3",
            "height_cm": "187cm",
            "weight_kg": "81kg",
            "matches": "12",
            "goals": "0",
            "jleague_debut": "2022/9/16",
            "jleague_first_goal": "",
            "national_team_caps": "5",
            "strong_points": ["ハイボール処理"],
            "season_stats": {"セーブ数": 33},
            "career_history": [],
        }
        parsed = parse_player_record(raw_player, {})
        self.assertEqual(parsed["player_id"], "P_KAS_1_早川友基")
        self.assertEqual(parsed["canonical_name"], "早川 友基")
        self.assertEqual(parsed["team_id"], "KAS")
        self.assertEqual(parsed["position"], "GK")
        self.assertEqual(parsed["number"], 1)
        self.assertEqual(parsed["height_cm"], 187)
        self.assertEqual(parsed["weight_kg"], 81)
        self.assertEqual(parsed["dominant_foot"], "右足")
        self.assertEqual(parsed["jleague_id"], "1632225")

        prof = json.loads(parsed["profile_json"])
        self.assertEqual(prof["birthplace"], "神奈川県")
        self.assertEqual(prof["strong_points"], ["ハイボール処理"])

    def test_ensure_schema_and_upsert(self) -> None:
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()

        # Create basic table as initially set up
        cur.execute("""
            CREATE TABLE entity_master_players (
                player_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                team_id TEXT NOT NULL,
                position TEXT,
                number INTEGER,
                en_name TEXT,
                aliases_json TEXT
            );
        """)

        ensure_schema(cur)

        # Calling again must be idempotent
        ensure_schema(cur)

        records = [
            {
                "player_id": "P_FCT_2_室屋成",
                "canonical_name": "室屋 成",
                "team_id": "FCT",
                "position": "DF",
                "number": 2,
                "en_name": "MUROYA Sei",
                "aliases_json": json.dumps(["室屋 成", "室屋成"]),
                "jleague_id": "12345",
                "birthdate": "1994/4/5",
                "height_cm": 176,
                "weight_kg": 70,
                "dominant_foot": "右足",
                "photo_url": "https://example.com/muroya.jpg",
                "profile_json": json.dumps({"club_name": "ＦＣ東京"}),
            },
        ]
        count = upsert_player_records(cur, records)
        self.assertEqual(count, 1)

        row = cur.execute(
            "SELECT player_id, canonical_name, height_cm, dominant_foot FROM entity_master_players WHERE player_id = 'P_FCT_2_室屋成'",
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "室屋 成")
        self.assertEqual(row[2], 176)
        self.assertEqual(row[3], "右足")

        conn.close()

    def test_run_enrichment_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_file = tmp_path / "test_football.db"
            players_file = tmp_path / "test_players.json"
            foot_file = tmp_path / "test_dominant_foot.json"

            # Init test DB
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE entity_master_players (
                    player_id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    position TEXT,
                    number INTEGER,
                    en_name TEXT,
                    aliases_json TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE player_match_stats (
                    match_id TEXT,
                    player_id TEXT,
                    player_name TEXT,
                    team_id TEXT,
                    number INTEGER
                );
            """)
            cur.execute(
                "INSERT INTO player_match_stats VALUES ('M01', 'P_FCT_2_室屋成', '室屋 成', 'FCT', 2);",
            )
            conn.commit()
            conn.close()

            # Create test raw files
            test_players = [
                {
                    "player_id": "12345",
                    "team_id": "FCT",
                    "name": "室屋 成",
                    "name_en": "MUROYA Sei",
                    "position": "DF",
                    "number": "2",
                    "dominant_foot": "",
                    "height_cm": "176",
                    "weight_kg": "70",
                    "birthdate": "1994/4/5",
                },
            ]
            with open(players_file, "w", encoding="utf-8") as f:
                json.dump(test_players, f)

            test_foot = {"players": {"室屋 成": "右足"}}
            with open(foot_file, "w", encoding="utf-8") as f:
                json.dump(test_foot, f)

            metrics = run_enrichment(
                db_path=db_file,
                all_players_path=players_file,
                dominant_foot_path=foot_file,
            )

            self.assertEqual(metrics["upserted_count"], 1)
            self.assertEqual(metrics["total_master_players"], 1)
            self.assertEqual(metrics["dominant_foot_count"], 1)
            self.assertEqual(metrics["height_count"], 1)
            self.assertEqual(metrics["stats_joined"], 1)
            self.assertEqual(metrics["join_rate"], 100.0)


if __name__ == "__main__":
    unittest.main()
