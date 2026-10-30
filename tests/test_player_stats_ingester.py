"""Unit tests for Step 2: pipeline/player_stats_ingester.py."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline.db import init_db
from pipeline.player_stats_ingester import (
    CanonicalPlayerResolver,
    build_match_player_and_team_records,
    ingest_all_2026_player_and_team_stats,
)


class TestPlayerStatsIngester(unittest.TestCase):
    """Test 3-source match telemetry merging, canonical player_id linking, and DB upsert."""

    def _create_sample_sources(self) -> tuple[dict, dict, dict, dict]:
        spaia_data = {
            "game_id": "2026080702",
            "player_stats": [
                {
                    "HV": 1,
                    "Uni": 17,
                    "Name": "小森　飛絢",
                    "Pos": "FW",
                    "StartF": "1",
                    "Time": 82,
                    "Score": 1,
                    "PKScore": 0,
                    "Assist": 0,
                    "PAPlayCount": 5,
                    "PASidePlayLCount": 2,
                    "PASidePlayRCount": 3,
                    "M30PlayCount": 9,
                    "At3rdPlayCount": 18,
                    "PassCount": 21,
                    "PassRate": 76.2,
                    "CrossCount": 2,
                    "DribbleCount": 3,
                    "TackleCount": 1,
                    "Yellow": 1,
                    "Red": 0,
                },
                {
                    "HV": 2,
                    "Uni": 5,
                    "Name": "中谷　進之介",
                    "Pos": "DF",
                    "StartF": "1",
                    "Time": 90,
                    "Score": 0,
                    "PKScore": 0,
                    "Assist": 0,
                    "PAPlayCount": 1,
                    "M30PlayCount": 4,
                    "At3rdPlayCount": 6,
                    "PassCount": 58,
                    "PassRate": 89.7,
                    "ClearCount": 7,
                    "TackleCount": 3,
                    "Yellow": 0,
                    "Red": 0,
                },
            ],
        }
        ystats_data = {
            "team_stats": {
                "home_team": "浦和",
                "away_team": "G大阪",
                "metrics": {
                    "保持率": {"浦和": "54.2%", "G大阪": "45.8%"},
                    "シュート": {"浦和": "14", "G大阪": "9"},
                    "枠内シュート": {"浦和": "6", "G大阪": "3"},
                    "走行距離": {"浦和": "114.5km", "G大阪": "112.1km"},
                    "スプリント": {"浦和": "152", "G大阪": "144"},
                    "パス（成功率）": {"浦和": "480(83.5%)", "G大阪": "410(79.0%)"},
                },
            },
            "player_stats": [
                {
                    "position": "FW",
                    "player_name": "小森 飛絢",
                    "team_name": "浦和",
                    "attack": {"shoot": "4", "shoot_on_target": "2", "goals": "1", "dribble_success": "2(66%)"},
                    "defense": {"tackle_success": "1(100%)", "loose_ball_recovery": "3", "block": "0", "clear": "1"},
                    "distance": {"total": "9.85", "first_half": "5.10", "second_half": "4.75"},
                    "sprint": {"total": "24", "first_half": "14", "second_half": "10", "max_speed": "34.2km/h"},
                    "pass": {"pass_success": "16(76.2%)", "attacking_third_pass": "9", "through_pass": "1", "cross": "2", "assist": "0"},
                    "plays_by_area": {"total": "35", "attacking_third": "22", "middle_third": "11", "defensive_third": "2"},
                    "set_pieces": {"fk": "0", "ck": "0"},
                    "discipline": {"yellow_card": "1", "red_card": "0", "foul": "2", "suffer_foul": "3"},
                },
                {
                    "position": "DF",
                    "player_name": "中谷 進之介",
                    "team_name": "G大阪",
                    "attack": {"shoot": "0", "shoot_on_target": "0", "goals": "0", "dribble_success": "0"},
                    "defense": {"tackle_success": "3(100%)", "loose_ball_recovery": "6", "block": "2", "clear": "7"},
                    "distance": {"total": "10.12", "first_half": "5.02", "second_half": "5.10"},
                    "sprint": {"total": "13", "first_half": "6", "second_half": "7", "max_speed": "31.8km/h"},
                    "pass": {"pass_success": "52(89.7%)", "attacking_third_pass": "4", "through_pass": "0", "cross": "0", "assist": "0"},
                    "plays_by_area": {"total": "72", "attacking_third": "5", "middle_third": "32", "defensive_third": "35"},
                    "set_pieces": {"fk": "1", "ck": "0"},
                    "discipline": {"yellow_card": "0", "red_card": "0", "foul": "1", "suffer_foul": "1"},
                },
            ],
        }
        flab_data = {
            "data": {
                "stats": [
                    {"name": "ゴール期待値", "home_val": "1.82", "away_val": "0.94"},
                ],
                "cbp": {
                    "player_matrix": [
                        {
                            "player_name": "小森　飛絢",
                            "team_side": "HOME",
                            "attack": 4.2,
                            "defense": 0.3,
                            "gain": 1.1,
                            "shoot": 3.5,
                        },
                        {
                            "player_name": "中谷　進之介",
                            "team_side": "AWAY",
                            "attack": 1.2,
                            "defense": 5.8,
                            "gain": 4.4,
                        },
                    ],
                },
                "timeline_blocks": [],
                "heatmaps": [{}, {}],
            },
        }
        summary_data = {
            "lineup": {
                "home": {"starters": [{"number": "17", "player_name": "小森 飛絢", "registered_pos": "FW"}], "bench": []},
                "away": {"starters": [{"number": "5", "player_name": "中谷 進之介", "registered_pos": "DF"}], "bench": []},
            },
        }
        return (spaia_data, ystats_data, flab_data, summary_data)

    def test_merge_3_sources_and_canonical_id(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE entity_master_players (
                player_id TEXT PRIMARY KEY,
                team_id TEXT,
                number INTEGER,
                canonical_name TEXT,
                aliases_json TEXT
            );
            """,
        )
        conn.execute(
            "INSERT INTO entity_master_players VALUES ('P_URA_17_小森飛絢', 'URA', 17, '小森 飛絢', '[\"小森飛絢\"]');",
        )
        conn.execute(
            "INSERT INTO entity_master_players VALUES ('P_GAM_20_中谷進之介', 'GAM', 20, '中谷 進之介', '[\"中谷進之介\"]');",
        )
        resolver = CanonicalPlayerResolver(conn)

        spaia_d, ystats_d, flab_d, sum_d = self._create_sample_sources()
        p_recs, t_recs = build_match_player_and_team_records(
            match_id="20260807_URA_GAM",
            home_team_id="URA",
            away_team_id="GAM",
            home_score=1,
            away_score=0,
            spaia_data=spaia_d,
            ystats_data=ystats_d,
            flab_data=flab_d,
            summary_data=sum_d,
            resolver=resolver,
        )

        self.assertEqual(len(p_recs), 2)
        komori = next(p for p in p_recs if p["team_id"] == "URA")
        nakatani = next(p for p in p_recs if p["team_id"] == "GAM")

        self.assertEqual(komori["player_id"], "P_URA_17_小森飛絢")
        self.assertEqual(nakatani["player_id"], "P_GAM_20_中谷進之介")
        self.assertEqual(komori["sprints"], 24)
        self.assertAlmostEqual(komori["distance_km"], 9.85)
        self.assertAlmostEqual(komori["cbp_points"], 5.6)

        k_raw = json.loads(komori["raw_stats_json"])
        self.assertAlmostEqual(k_raw["max_speed_kmh"], 34.2)
        self.assertEqual(k_raw["sprints_first_half"], 14)
        self.assertEqual(k_raw["plays_by_area"]["attacking_third"], 22)
        self.assertEqual(k_raw["discipline"]["yellow_cards"], 1)
        self.assertEqual(k_raw["spaia"]["pa_entries"], 5)

        self.assertEqual(len(t_recs), 2)
        ura_t = next(t for t in t_recs if t["team_id"] == "URA")
        self.assertAlmostEqual(ura_t["possession"], 54.2)
        self.assertAlmostEqual(ura_t["xg"], 1.82)
        self.assertEqual(ura_t["sprints"], 152)
        conn.close()

    def test_yahoo_fallback_when_spaia_empty_and_db_e2e(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            db_path = tdir / "test_football.db"
            y_dir = tdir / "yahoo"
            s_dir = tdir / "spaia"
            f_dir = tdir / "flab"
            y_dir.mkdir()
            s_dir.mkdir()
            f_dir.mkdir()

            conn = init_db(str(db_path))
            conn.execute("INSERT INTO entity_master_teams (team_id, canonical_name, short_name) VALUES ('URA', '浦和レッズ', '浦和');")
            conn.execute("INSERT INTO entity_master_teams (team_id, canonical_name, short_name) VALUES ('GAM', 'ガンバ大阪', 'G大阪');")
            conn.execute(
                "INSERT INTO entity_master_players (player_id, canonical_name, team_id, position, number) VALUES ('P_URA_17_小森飛絢', '小森 飛絢', 'URA', 'FW', 17);",
            )
            conn.execute(
                "INSERT INTO matches (match_id, season, matchweek, date, home_team_id, away_team_id, home_score, away_score) VALUES ('20260807_URA_GAM', 2026, 1, '2026-08-07', 'URA', 'GAM', 1, 0);",
            )
            conn.commit()
            conn.close()

            _, ystats_d, flab_d, sum_d = self._create_sample_sources()
            (y_dir / "20260807_URA_GAM_stats.json").write_text(json.dumps(ystats_d, ensure_ascii=False), encoding="utf-8")
            (y_dir / "20260807_URA_GAM_summary.json").write_text(json.dumps(sum_d, ensure_ascii=False), encoding="utf-8")
            (f_dir / "20260807_URA_GAM.json").write_text(json.dumps(flab_d, ensure_ascii=False), encoding="utf-8")

            res = ingest_all_2026_player_and_team_stats(
                db_path=db_path,
                yahoo_dir=y_dir,
                spaia_dir=s_dir,
                flab_dir=f_dir,
            )
            self.assertEqual(res["ingested_matches"], 1)
            self.assertEqual(res["total_player_rows"], 2)
            self.assertEqual(res["total_team_rows"], 2)


if __name__ == "__main__":
    unittest.main()

