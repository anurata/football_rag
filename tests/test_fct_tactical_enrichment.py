"""
Unit tests for FC Tokyo Tactical Enrichment and Objective Profiler Integration.
Verifies that all 12 FC Tokyo matches have high-fidelity, data-driven tactical JSONs,
no dummy placeholders (like '町田ゼルビア選手'), real player names, and rich 15-perspective integration.
"""

import unittest
import json
from pathlib import Path

from agent.objective_profiler import MatchObjectiveProfiler, resolve_team_name


class TestFctTacticalEnrichment(unittest.TestCase):
    """Test suite for FC Tokyo tactical data and 15-perspective profiler."""

    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).resolve().parent.parent
        cls.structured_dir = cls.root_dir / "data" / "structured"
        cls.profiler = MatchObjectiveProfiler()

        # All 12 FC Tokyo fixture match IDs
        cls.fct_match_ids = [
            "20260808_FCT_ZEL",
            "20260815_VOB_FCT",
            "20260821_FCT_JEF",
            "20260829_VVN_FCT",
            "20260902_PUL_FCT",
            "20260906_FCT_SAN",
            "20260912_GAM_FCT",
            "20260919_FCT_NAG",
            "20261010_FCT_URA",
            "20261017_VER_FCT",
            "20261021_FCT_REY",
            "20261025_FCT_MIT",
        ]

    def test_structured_files_exist(self):
        """Verify that all 12 FC Tokyo tactical JSON files exist."""
        for match_id in self.fct_match_ids:
            target_path = self.structured_dir / f"{match_id}_tactical.json"
            self.assertTrue(
                target_path.exists(),
                f"Missing tactical file: {target_path}",
            )

    def test_no_dummy_placeholders_in_tactical_json(self):
        """Verify that no dummy placeholders like '町田ゼルビア選手' exist."""
        for match_id in self.fct_match_ids:
            target_path = self.structured_dir / f"{match_id}_tactical.json"
            content = target_path.read_text(encoding="utf-8")
            self.assertNotIn("町田ゼルビア選手", content, f"Found placeholder in {match_id}")
            self.assertNotIn("FC東京選手", content, f"Found placeholder in {match_id}")

    def test_real_player_names_and_events(self):
        """Verify that key events and highlights contain verified real player names."""
        # e.g., 20260808_FCT_ZEL must have Marcelo Ryan, Mitchell Duke, Soma, etc.
        zel_file = self.structured_dir / "20260808_FCT_ZEL_tactical.json"
        data = json.loads(zel_file.read_text(encoding="utf-8"))

        hls = " ".join(data.get("tactical_highlights", []))
        self.assertIn("マルセロ ヒアン", hls)
        self.assertIn("橋本 健人", hls)
        self.assertIn("松橋 力蔵監督", hls)
        self.assertIn("黒田 剛監督", hls)

        phases = data.get("phases", [])
        self.assertEqual(len(phases), 6)
        # Phase 0-15 should describe actual match opening
        self.assertIn("キム スンギュ", phases[0]["momentum_summary"])

    def test_profiler_integrates_tactical_data(self):
        """Verify that MatchObjectiveProfiler builds rich 15 perspectives using tactical data."""
        mock_summary = {
            "match": {
                "match_id": "20260808_FCT_ZEL",
                "home_team_id": "FCT",
                "away_team_id": "ZEL",
                "home_score": 1,
                "away_score": 5,
            },
            "team_stats": {
                "FCT": {"shots": 9, "shots_on_target": 3, "possession": 48.0},
                "ZEL": {"shots": 16, "shots_on_target": 8, "possession": 52.0},
            },
            "events": [
                {"event_type": "GOAL", "team_id": "FCT", "player_name": "マルセロ ヒアン", "minute": 5},
                {"event_type": "GOAL", "team_id": "ZEL", "player_name": "ミッチェル デューク", "minute": 27},
            ],
        }

        report = self.profiler.build_15_perspective_report(mock_summary)
        struct_summary = report.get("overall_structure_summary", {})
        narrative = struct_summary.get("narrative", "")

        # Highlights should be injected into narrative
        self.assertIn("【主要戦術ハイライト＆決定打】", narrative)
        self.assertIn("橋本 健人の一発退場", narrative)

        # 15 perspectives check
        perspectives = report.get("perspectives", [])
        self.assertEqual(len(perspectives), 15)

        # Game flow layer 2 should contain exact events
        gf = perspectives[0]
        self.assertIn("マルセロ ヒアン", gf["layer2_counts"])

        # Win/Loss report check
        wl = self.profiler.build_win_loss_report(mock_summary)
        away_loss_reasons = wl["away"]["loss_reasons"]
        self.assertTrue(
            any("退場" in r for r in away_loss_reasons),
            f"Expected red card in loss reasons: {away_loss_reasons}",
        )


if __name__ == "__main__":
    unittest.main()
