"""
Unit tests for agent/objective_profiler.py, agent/qualitative_comparator.py,
and agent/player_rater.py.
"""

import unittest
from agent.objective_profiler import MatchObjectiveProfiler
from agent.qualitative_comparator import QualitativeComparator
from agent.player_rater import PlayerRatingGenerator


class TestObjectiveProfilerAndComparator(unittest.TestCase):
    """Test suite for objective profiler, qualitative comparator, and player rater."""

    def setUp(self):
        self.profiler = MatchObjectiveProfiler()
        self.comparator = QualitativeComparator()
        self.rater = PlayerRatingGenerator()

        self.sample_match_summary = {
            "match": {
                "match_id": "20261025_FCT_MIT",
                "home_team_id": "FCT",
                "away_team_id": "MIT",
                "home_score": 6,
                "away_score": 0,
                "date": "2026-10-25",
                "matchweek": 34,
            },
            "team_stats": {
                "FCT": {
                    "shots": 23,
                    "shots_on_target": 11,
                    "xg": 2.296,
                    "possession": 53.4,
                },
                "MIT": {
                    "shots": 12,
                    "shots_on_target": 2,
                    "xg": 0.649,
                    "possession": 46.6,
                },
            },
        }

    def test_build_15_perspective_report(self):
        """Verify generation of all 15 objective perspectives."""
        result = self.profiler.build_15_perspective_report(self.sample_match_summary)
        self.assertIn("perspectives", result)
        perspectives = result["perspectives"]
        self.assertEqual(len(perspectives), 15)

        # Check essential perspectives exist
        p_ids = [p["perspective_id"] for p in perspectives]
        self.assertIn("game_flow", p_ids)
        self.assertIn("xg_skill_vs_luck", p_ids)
        self.assertIn("field_tilt", p_ids)
        self.assertIn("pressing_intensity", p_ids)
        self.assertIn("spatial_5_lane", p_ids)
        self.assertIn("substitution_impact", p_ids)

        # Check layers structure
        for p in perspectives:
            self.assertIn("name", p)
            self.assertIn("applicable_layers", p)
            self.assertIn("summary", p)
            self.assertIn("layer1_data", p)

    def test_build_win_loss_report(self):
        """Verify win/loss, improvement, and continuity generation for both teams."""
        result = self.profiler.build_win_loss_report(self.sample_match_summary)
        self.assertIn("home", result)
        self.assertIn("away", result)

        home = result["home"]
        self.assertEqual(home["team_id"], "FC東京")
        self.assertGreaterEqual(len(home["win_reasons"]), 2)
        self.assertGreaterEqual(len(home["improvements"]), 2)
        self.assertGreaterEqual(len(home["continuity"]), 1)

        away = result["away"]
        self.assertEqual(away["team_id"], "水戸ホーリーホック")
        self.assertGreaterEqual(len(away["loss_reasons"]), 2)
        self.assertGreaterEqual(len(away["improvements"]), 2)
        self.assertGreaterEqual(len(away["continuity"]), 1)

    def test_build_5_advanced_reports(self):
        """Verify all 5 specialized tactical reports are generated."""
        result = self.profiler.build_5_advanced_reports(self.sample_match_summary)
        self.assertIn("report_1_spatial_54", result)
        self.assertIn("report_2_archetypes", result)
        self.assertIn("report_3_units", result)
        self.assertIn("report_4_scouting", result)
        self.assertIn("report_5_what_if", result)

        self.assertGreaterEqual(len(result["report_2_archetypes"]["players"]), 4)
        self.assertGreaterEqual(len(result["report_3_units"]["units"]), 3)
        self.assertGreaterEqual(len(result["report_5_what_if"]["scenarios"]), 2)

    def test_qualitative_comparator(self):
        """Verify qualitative comparator extracts alignments, gaps, and hidden truths."""
        mock_reviews = [
            {"review_type": "OFFICIAL_REPORT", "title": "マッチレポート", "content_text": "..."},
        ]
        obj_report = self.profiler.build_15_perspective_report(self.sample_match_summary)
        comp_result = self.comparator.compare_facts_with_reviews(
            match_id="20261025_FCT_MIT",
            objective_report=obj_report,
            reviews=mock_reviews,
        )

        self.assertIn("alignments", comp_result)
        self.assertIn("perception_gaps", comp_result)
        self.assertIn("hidden_truths", comp_result)

        self.assertGreaterEqual(len(comp_result["alignments"]), 3)
        self.assertGreaterEqual(len(comp_result["perception_gaps"]), 2)
        self.assertGreaterEqual(len(comp_result["hidden_truths"]), 1)

    def test_player_rater(self):
        """Verify player rating generator produces MOM, player list, and coach ratings."""
        ratings = self.rater.generate_match_ratings(self.sample_match_summary)
        self.assertIn("mom", ratings)
        self.assertIn("home_players", ratings)
        self.assertIn("away_players", ratings)
        self.assertIn("coaches", ratings)

        # Check MOM
        self.assertEqual(ratings["mom"]["player_name"], "安斎 颯馬")
        self.assertGreaterEqual(ratings["mom"]["rating"], 7.5)

        # Check player counts
        self.assertGreaterEqual(len(ratings["home_players"]), 11)
        self.assertGreaterEqual(len(ratings["away_players"]), 11)

        # Check coach ratings
        self.assertIn("home_coach", ratings["coaches"])
        self.assertIn("away_coach", ratings["coaches"])


    def test_team_name_resolution(self):
        """Verify team code properly resolves to canonical Japanese name."""
        from agent.objective_profiler import resolve_team_name
        self.assertEqual(resolve_team_name("FCT"), "FC東京")
        self.assertEqual(resolve_team_name("MIT"), "水戸ホーリーホック")
        self.assertEqual(resolve_team_name("KAS"), "鹿島アントラーズ")
        self.assertEqual(resolve_team_name("UNKNOWN_CLUB"), "UNKNOWN_CLUB")

    def test_overall_structure_summary_and_away_perspective(self):
        """Verify Step 88 rich overall structure summary and away team perspectives."""
        obj_report = self.profiler.build_15_perspective_report(self.sample_match_summary)
        self.assertIn("overall_structure_summary", obj_report)
        struct = obj_report["overall_structure_summary"]
        self.assertIn("narrative", struct)
        self.assertEqual(len(struct.get("phases", [])), 3)

        perspectives = obj_report.get("perspectives", [])
        self.assertEqual(len(perspectives), 15)
        # Check first perspective has away_perspective and theory
        p1 = perspectives[0]
        self.assertIn("away_perspective", p1)
        self.assertIn("layer3_theory", p1)
        self.assertIn("layer2_counts", p1)


if __name__ == "__main__":
    unittest.main()
