"""
Unit tests for bug fixes and data fallback in agent/objective_profiler.py.
Verifies:
1. Win/loss label mapping and outcome accuracy across win, loss, and draw.
2. Fallback resolution for player CBP rankings, top gainers, and passers (no empty strings).
3. Substitution bench impact fallback (no 0.0 CBP).
4. Full momentum string generation (no ugly ellipsis).
5. Bilateral perspectives (both home_perspective and away_perspective present).
"""

import unittest
from agent.objective_profiler import MatchObjectiveProfiler


class TestObjectiveProfilerBugs(unittest.TestCase):
    """Test suite for Step 1 bug fixes in MatchObjectiveProfiler."""

    def setUp(self):
        self.profiler = MatchObjectiveProfiler()
        self.oka_fct_summary = {
            "match": {
                "match_id": "20261031_OKA_FCT",
                "home_team_id": "OKA",
                "away_team_id": "FCT",
                "home_score": 0,
                "away_score": 4,
            },
            "team_stats": {
                "OKA": {
                    "shots": 7,
                    "shots_on_target": 2,
                    "possession": 44.0,
                    "total_distance_km": 112.0,
                    "sprints": 130,
                    "xg": 0.28,
                },
                "FCT": {
                    "shots": 16,
                    "shots_on_target": 8,
                    "possession": 56.0,
                    "total_distance_km": 110.5,
                    "sprints": 125,
                    "xg": 2.20,
                },
            },
            "events": [
                {
                    "minute": 18,
                    "team_id": "FCT",
                    "player_name": "荒木 遼太郎",
                    "event_type": "GOAL",
                },
                {
                    "minute": 34,
                    "team_id": "FCT",
                    "player_name": "佐藤 恵允",
                    "event_type": "GOAL",
                },
                {
                    "minute": 58,
                    "team_id": "FCT",
                    "player_name": "長倉 幹樹",
                    "event_type": "GOAL",
                },
                {
                    "minute": 79,
                    "team_id": "FCT",
                    "player_name": "常盤 亨太",
                    "event_type": "GOAL",
                },
            ],
        }

    def test_win_loss_outcome_away_win(self):
        """0-4 match must mark AWAY as winner and HOME as loser."""
        wl = self.profiler.build_win_loss_report(self.oka_fct_summary)
        h = wl["home"]
        a = wl["away"]

        self.assertEqual(h["outcome"], "LOSS")
        self.assertTrue(h["is_loser"])
        self.assertFalse(h["is_winner"])
        self.assertTrue(len(h["loss_reasons"]) > 0)
        self.assertEqual(len(h["win_reasons"]), 0)

        self.assertEqual(a["outcome"], "WIN")
        self.assertTrue(a["is_winner"])
        self.assertFalse(a["is_loser"])
        self.assertTrue(len(a["win_reasons"]) > 0)
        self.assertEqual(len(a["loss_reasons"]), 0)

    def test_win_loss_outcome_home_win(self):
        """2-0 match must mark HOME as winner and AWAY as loser."""
        summary = {
            "match": {
                "match_id": "20261031_OKA_FCT_TEST",
                "home_team_id": "OKA",
                "away_team_id": "FCT",
                "home_score": 2,
                "away_score": 0,
            },
            "team_stats": {
                "OKA": {"shots": 10, "shots_on_target": 5},
                "FCT": {"shots": 5, "shots_on_target": 1},
            },
            "events": [],
        }
        wl = self.profiler.build_win_loss_report(summary)
        self.assertEqual(wl["home"]["outcome"], "WIN")
        self.assertTrue(wl["home"]["is_winner"])
        self.assertEqual(wl["away"]["outcome"], "LOSS")
        self.assertTrue(wl["away"]["is_loser"])

    def test_win_loss_outcome_draw(self):
        """1-1 match must mark both as DRAW."""
        summary = {
            "match": {
                "match_id": "20261031_OKA_FCT_DRAW",
                "home_team_id": "OKA",
                "away_team_id": "FCT",
                "home_score": 1,
                "away_score": 1,
            },
            "team_stats": {
                "OKA": {"shots": 8, "shots_on_target": 3},
                "FCT": {"shots": 8, "shots_on_target": 3},
            },
            "events": [],
        }
        wl = self.profiler.build_win_loss_report(summary)
        self.assertEqual(wl["home"]["outcome"], "DRAW")
        self.assertTrue(wl["home"]["is_draw"])
        self.assertEqual(wl["away"]["outcome"], "DRAW")
        self.assertTrue(wl["away"]["is_draw"])

    def test_perspectives_no_empty_variables_and_bilateral(self):
        """All 15 perspectives must avoid empty variables and have bilateral viewpoints."""
        report = self.profiler.build_15_perspective_report(self.oka_fct_summary)
        perspectives = report.get("perspectives", [])
        self.assertEqual(len(perspectives), 15)

        p_map = {p["perspective_id"]: p for p in perspectives}

        # Check bilateral perspective notes
        for p in perspectives:
            self.assertIn("home_perspective", p, f"Missing home_perspective in {p['perspective_id']}")
            self.assertIn("away_perspective", p, f"Missing away_perspective in {p['perspective_id']}")
            self.assertTrue(len(p["home_perspective"]) > 5)
            self.assertTrue(len(p["away_perspective"]) > 5)

        # Perspective 3: field_tilt (should not be empty or raw '0%' default without context)
        p3 = p_map["field_tilt"]
        self.assertNotIn(" 0% (", p3["layer1_data"]["conv_30_to_pa"])
        self.assertNotIn(" 0% (", p3["layer1_data"]["conv_pa_to_shot"])


        # Perspective 6: substitution_impact
        p6 = p_map["substitution_impact"]
        self.assertNotIn("0.0", p6["layer1_data"]["home_bench_impact"])
        self.assertNotIn("0.0", p6["layer1_data"]["away_bench_impact"])

        # Perspective 7: phase_momentum_styles
        p7 = p_map["phase_momentum_styles"]
        self.assertNotIn("... -> ...", p7["layer1_data"]["momentum"])

        # Perspective 9: unsung_hero
        p9 = p_map["unsung_hero"]
        top_gain_h = p9["layer1_data"]["top_gain_home"]
        top_gain_a = p9["layer1_data"]["top_gain_away"]
        self.assertTrue(len(top_gain_h.strip()) > 3)
        self.assertTrue(len(top_gain_a.strip()) > 3)

        # Perspective 13: progressive_passes
        p13 = p_map["progressive_passes"]
        top_pass_h = p13["layer1_data"]["top_pass_home"]
        top_pass_a = p13["layer1_data"]["top_pass_away"]
        self.assertTrue(len(top_pass_h.strip()) > 3)
        self.assertTrue(len(top_pass_a.strip()) > 3)

    def test_55_tactical_metrics_integration(self):
        """Verify that 55 tactical metrics and specific Layer 2/3 features are integrated."""
        report = self.profiler.build_15_perspective_report(self.oka_fct_summary)
        perspectives = report.get("perspectives", [])
        p_map = {p["perspective_id"]: p for p in perspectives}

        # Perspective 1: game flow timeline and pass tempo
        p1 = p_map["game_flow"]
        self.assertIn("15分毎xG推移", p1["layer1_data"]["time_phase_xg"])
        self.assertIn("18分", p1["layer2_key_plays"])
        self.assertIn("79分", p1["layer2_key_plays"])

        # Perspective 2: xG & shot quality
        p2 = p_map["xg_skill_vs_luck"]
        self.assertIn("npxg", p2["layer1_data"])
        self.assertIn("xgot", p2["layer1_data"])
        self.assertIn("shot_quality", p2["layer1_data"])
        self.assertIn("0.138", p2["layer1_data"]["shot_quality"])
        self.assertIn("0.040", p2["layer1_data"]["shot_quality"])

        # Perspective 3: Field Tilt & Deep Completions
        p3 = p_map["field_tilt"]
        self.assertIn("deep_completions", p3["layer1_data"])
        self.assertIn("box_touches", p3["layer1_data"])
        self.assertIn("敵陣30m内パスシェア", p3["layer1_data"]["field_tilt"])


        # Perspective 4: PPDA & Direct Speed
        p4 = p_map["pressing_intensity"]
        self.assertIn("ppda", p4["layer1_data"])
        self.assertIn("direct_speed", p4["layer1_data"])
        self.assertIn("8.4", p4["layer1_data"]["ppda"])

        # Perspective 5: 5-lane spatial distribution
        p5 = p_map["spatial_5_lane"]
        self.assertIn("attack_lanes", p5["layer1_data"])
        self.assertIn("halfspace_entries", p5["layer1_data"])

        # Perspective 8: Game State DNA
        p8 = p_map["game_state_dna"]
        self.assertIn("draw_state_stats", p8["layer1_data"])
        self.assertIn("lead_state_stats", p8["layer1_data"])

        # Perspective 12: Defensive Compactness
        p12 = p_map["defensive_compactness"]
        self.assertIn("convex_hull", p12["layer1_data"])
        self.assertIn("stretch_index", p12["layer1_data"])

        # Perspective 13: Progressive passes & BPI
        p13 = p_map["progressive_passes"]
        self.assertIn("bpi", p13["layer1_data"])
        self.assertIn("linebreaks", p13["layer1_data"])

        # Perspective 14: Individual Duels
        p14 = p_map["individual_duels"]
        self.assertIn("ground_duels", p14["layer1_data"])
        self.assertIn("aerial_duels", p14["layer1_data"])

        # Perspective 15: Stamina Dropoff
        p15 = p_map["stamina_dropoff"]
        self.assertIn("sprint_dropoff", p15["layer1_data"])
        self.assertIn("late_sprints", p15["layer1_data"])



if __name__ == "__main__":
    unittest.main()
