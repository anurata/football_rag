"""全20クラブ戦術プロファイル完全性および選手アーキタイプ割り当て検証テスト (tests/test_team_profiles_and_archetypes.py)."""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

from pipeline.tactical_matchup_engine import TacticalMatchupEngine

ROOT_DIR = Path(__file__).resolve().parent.parent
TEAM_PROFILES_PATH = ROOT_DIR / "knowledge" / "team_tactical_profiles.json"
ARCHETYPE_ASSIGNMENTS_PATH = ROOT_DIR / "knowledge" / "player_archetype_assignments.json"
DB_PATH = ROOT_DIR / "data" / "football.db"

ALL_20_CLUBS = {
    "CER", "FCT", "FUK", "GAM", "HIR", "JEF", "KAS", "KAW", "MAR", "MIT",
    "NAG", "OKA", "PUL", "REY", "SAN", "URA", "VER", "VOB", "VVN", "ZEL",
}


class TestTeamProfilesAndArchetypes(unittest.TestCase):
    """全20クラブの戦術プロファイル完全性と選手アーキタイプ紐づけを検証する."""

    def test_team_profiles_all_20_clubs_complete(self) -> None:
        """全20クラブのプロファイルが存在し、必須戦術セクションが100%充足されていることを検証."""
        self.assertTrue(TEAM_PROFILES_PATH.exists(), "team_tactical_profiles.json must exist")
        data = json.loads(TEAM_PROFILES_PATH.read_text(encoding="utf-8"))
        teams = data.get("teams", {})

        self.assertEqual(set(teams.keys()), ALL_20_CLUBS)

        for tid in ALL_20_CLUBS:
            t = teams[tid]
            self.assertEqual(t.get("team_id"), tid)
            self.assertTrue(t.get("team_name"), f"Team name missing for {tid}")
            self.assertTrue(t.get("manager"), f"Manager missing for {tid}")
            self.assertTrue(t.get("base_formation"), f"Base formation missing for {tid}")

            # in_possession
            in_p = t.get("in_possession", {})
            self.assertTrue(in_p.get("build_up_style"), f"in_possession.build_up_style missing for {tid}")
            self.assertTrue(in_p.get("summary"), f"in_possession.summary missing for {tid}")

            # out_of_possession
            out_p = t.get("out_of_possession", {})
            self.assertTrue(out_p.get("defensive_line"), f"out_of_possession.defensive_line missing for {tid}")
            self.assertTrue(out_p.get("summary"), f"out_of_possession.summary missing for {tid}")

            # transitions & structural vulnerabilities
            trans = t.get("transitions", {})
            self.assertTrue(trans.get("positive"), f"transitions.positive missing for {tid}")
            self.assertTrue(trans.get("negative"), f"transitions.negative missing for {tid}")

            vulns = t.get("structural_vulnerabilities", [])
            self.assertGreaterEqual(len(vulns), 2, f"Vulnerabilities should have >= 2 items for {tid}")

            # evidences
            evs = t.get("evidences", [])
            self.assertGreaterEqual(len(evs), 6, f"Evidences should have >= 6 items for {tid}")

    def test_team_profiles_manager_and_formation_valid(self) -> None:
        """主要クラブの監督名および実フォーメーション最頻値が2026年実績と合致していることを検証."""
        data = json.loads(TEAM_PROFILES_PATH.read_text(encoding="utf-8"))
        teams = data.get("teams", {})

        # FC東京
        self.assertEqual(teams["FCT"]["manager"], "松橋 力蔵")
        self.assertEqual(teams["FCT"]["base_formation"], "4-4-2")

        # サンフレッチェ広島
        self.assertEqual(teams["HIR"]["base_formation"], "3-4-2-1")

        # 浦和レッズ
        self.assertIn(teams["URA"]["base_formation"], ["4-1-2-3", "3-4-2-1", "4-4-2"])

        # 町田ゼルビア
        self.assertEqual(teams["ZEL"]["manager"], "黒田 剛")

    def test_player_archetype_assignments_complete(self) -> None:
        """全20クラブの出場選手にアーキタイプが決定論的に割り当てられていることを検証."""
        self.assertTrue(ARCHETYPE_ASSIGNMENTS_PATH.exists(), "player_archetype_assignments.json must exist")
        data = json.loads(ARCHETYPE_ASSIGNMENTS_PATH.read_text(encoding="utf-8"))

        self.assertGreaterEqual(data.get("total_players_assigned", 0), 500)
        teams = data.get("teams", {})
        self.assertEqual(set(teams.keys()), ALL_20_CLUBS)

        for tid in ALL_20_CLUBS:
            players = teams[tid]
            self.assertGreaterEqual(len(players), 15, f"{tid} should have >= 15 assigned players")

            # 主力選手に primary_archetype が付与されていること
            for p in players[:5]:
                self.assertTrue(p.get("primary_archetype"), f"Missing primary archetype for {p.get('name')}")
                self.assertTrue(p.get("primary_archetype_name"))

    def test_entity_master_players_profile_json_updated(self) -> None:
        """entity_master_players の profile_json に archetypes が保存されていることを検証."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            rows = cur.execute(
                """
                SELECT player_id, canonical_name, profile_json
                FROM entity_master_players
                WHERE dominant_foot IS NOT NULL
                LIMIT 20
                """,
            ).fetchall()
            self.assertGreater(len(rows), 0)

            for r in rows:
                self.assertIsNotNone(r["profile_json"], f"profile_json should not be None for {r['canonical_name']}")
                prof = json.loads(r["profile_json"])
                self.assertIn("archetypes", prof, f"archetypes key missing for {r['canonical_name']}")
                arch = prof["archetypes"]
                self.assertTrue(arch.get("primary"), f"primary archetype missing for {r['canonical_name']}")
        finally:
            conn.close()

    def test_tactical_matchup_engine_with_new_profiles(self) -> None:
        """TacticalMatchupEngine が更新後プロファイルを正常に読み込んでミスマッチを抽出できることを検証."""
        engine = TacticalMatchupEngine()
        res = engine.analyze_match_mismatches("20260807_GAM_URA")
        self.assertIn("mismatches", res)
        self.assertGreater(len(res["mismatches"]), 0)


if __name__ == "__main__":
    unittest.main()

