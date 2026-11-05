# -*- coding: utf-8 -*-
"""
Tests for MatchReportCardCalculator (tests/test_match_report_card_calculator.py).
Conforms to Python standard library unittest.
"""

import sqlite3
import unittest
from pathlib import Path

from pipeline.match_report_card_calculator import MatchReportCardCalculator

DB_PATH = Path("data/football.db")


class TestMatchReportCardCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = MatchReportCardCalculator()

    def test_derby_detection(self):
        """Test derby match recognition."""
        self.assertEqual(self.calc.is_derby_match("MAR", "KAW"), "神奈川ダービー")
        self.assertEqual(self.calc.is_derby_match("KAW", "MAR"), "神奈川ダービー")
        self.assertEqual(self.calc.is_derby_match("FCT", "KAW"), "多摩川クラシコ")
        self.assertEqual(self.calc.is_derby_match("GAM", "CER"), "大阪ダービー")
        self.assertEqual(self.calc.is_derby_match("REY", "JEF"), "千葉ダービー")
        self.assertIsNone(self.calc.is_derby_match("FCT", "SAN"))

    def test_rank_determination(self):
        """Test S to D rank determination."""
        self.assertEqual(self.calc._determine_rank(55), "S")
        self.assertEqual(self.calc._determine_rank(49), "S")
        self.assertEqual(self.calc._determine_rank(48), "A+")
        self.assertEqual(self.calc._determine_rank(43), "A+")
        self.assertEqual(self.calc._determine_rank(42), "A-")
        self.assertEqual(self.calc._determine_rank(37), "A-")
        self.assertEqual(self.calc._determine_rank(36), "B+")
        self.assertEqual(self.calc._determine_rank(31), "B+")
        self.assertEqual(self.calc._determine_rank(30), "B-")
        self.assertEqual(self.calc._determine_rank(25), "B-")
        self.assertEqual(self.calc._determine_rank(24), "C")
        self.assertEqual(self.calc._determine_rank(13), "C")
        self.assertEqual(self.calc._determine_rank(12), "D")
        self.assertEqual(self.calc._determine_rank(0), "D")

    def test_excitement_index_derby_and_comeback(self):
        """Test excitement index calculation with derby and comeback bonuses."""
        events = [
            {"event_type": "goal", "team_id": "KAW", "minute": 15},
            {"event_type": "goal", "team_id": "MAR", "minute": 60},
            {"event_type": "goal", "team_id": "MAR", "minute": 88},
        ]
        t_flab = {"xg": 2.1, "shots_on_target": 6, "sprints": 130}
        o_flab = {"xg": 1.2, "shots_on_target": 4, "sprints": 120}

        score, details = self.calc._calc_excitement_index(
            team_id="MAR",
            opp_id="KAW",
            team_score=2,
            opp_score=1,
            events=events,
            t_flab=t_flab,
            o_flab=o_flab,
            is_home=True,
        )

        # Raw unscaled score before final clamping/scaling
        self.assertGreaterEqual(score, 10.0)
        self.assertTrue(any("神奈川ダービー" in r for r in details["reasons"]))
        self.assertTrue(any("逆転勝利" in r for r in details["reasons"]))
        self.assertTrue(any("80分以降" in r for r in details["reasons"]))

    def test_scaling_factor(self):
        """Test outcome and goal-difference scaling factor (gamma)."""
        # Big win (+3 or more) -> 1.10
        self.assertAlmostEqual(self.calc.compute_outcome_decay_factor(team_score=4, opp_score=0), 1.10)
        # Moderate win (+2) -> 1.05
        self.assertAlmostEqual(self.calc.compute_outcome_decay_factor(team_score=3, opp_score=1), 1.05)
        # 1-goal win (+1) -> 1.00
        self.assertAlmostEqual(self.calc.compute_outcome_decay_factor(team_score=2, opp_score=1), 1.00)
        # Draw (0) -> 0.90
        self.assertAlmostEqual(self.calc.compute_outcome_decay_factor(team_score=1, opp_score=1), 0.90)
        # 1-goal loss (-1) -> 0.80
        self.assertAlmostEqual(self.calc.compute_outcome_decay_factor(team_score=1, opp_score=2), 0.80)
        # 2-goal loss (-2) -> 0.72
        self.assertAlmostEqual(self.calc.compute_outcome_decay_factor(team_score=0, opp_score=2), 0.72)
        # Big loss (-3 or more) -> 0.65
        self.assertAlmostEqual(self.calc.compute_outcome_decay_factor(team_score=0, opp_score=4), 0.65)

    def test_metrics_sum_equals_total_score(self):
        """Test that sum of 6 rounded metrics strictly equals total_score."""
        if not DB_PATH.exists():
            self.skipTest("data/football.db not found")

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT match_id, home_team_id, away_team_id FROM matches WHERE matchweek = 13 LIMIT 3")
        rows = cur.fetchall()
        conn.close()

        for mid, home, away in rows:
            for tid in (home, away):
                card = self.calc.calculate_report_card(mid, tid)
                m_sum = sum(v["score"] for v in card["metrics"].values())
                self.assertEqual(
                    card["total_score"],
                    m_sum,
                    f"Mismatch in {mid} for {tid}: total={card['total_score']} vs sum={m_sum}",
                )

    def test_calculate_actual_match(self):
        """Test calculation on real match data in database."""
        if not DB_PATH.exists():
            self.skipTest("data/football.db not found")

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT match_id, home_team_id, away_team_id FROM matches LIMIT 1")
        row = cur.fetchone()
        conn.close()

        if not row:
            self.skipTest("No matches found in DB")

        match_id, home_team, away_team = row
        report = self.calc.calculate_report_card(match_id, home_team)

        self.assertEqual(report["match_id"], match_id)
        self.assertEqual(report["team_id"], home_team)
        self.assertTrue(0 <= report["total_score"] <= 60)
        self.assertIn(report["rank"], ["S", "A+", "A-", "B+", "B-", "C", "D"])

        metrics = report["metrics"]
        for m_key in [
            "game_dominance",
            "individual_power",
            "style_execution",
            "duels_intensity",
            "team_cohesion",
            "excitement_index",
        ]:
            self.assertIn(m_key, metrics)
            sc = metrics[m_key]["score"]
            self.assertTrue(0 <= sc <= 10, f"{m_key} score {sc} out of bounds")


if __name__ == "__main__":
    unittest.main()
