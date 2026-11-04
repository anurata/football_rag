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

        # 5.0 (base) + 1.5 (derby win) + 1.5 (comeback win) + 1.5 (late goal) + 0.5 (high xG 3.3) + 0.5 (sprints 250) + 0.5 (3 goals) = 11.0 -> clamped to 10
        self.assertEqual(score, 10)
        self.assertTrue(any("神奈川ダービー" in r for r in details["reasons"]))
        self.assertTrue(any("逆転勝利" in r for r in details["reasons"]))
        self.assertTrue(any("80分以降" in r for r in details["reasons"]))

    def test_outcome_calibration(self):
        """Test outcome-based calibration caps and floors."""
        # Victory floor
        self.assertEqual(self.calc._calibrate_total_score(30, team_score=2, opp_score=1), 37)
        self.assertEqual(self.calc._calibrate_total_score(35, team_score=3, opp_score=1), 42)
        # Defeat cap
        self.assertEqual(self.calc._calibrate_total_score(46, team_score=2, opp_score=3), 36)
        self.assertEqual(self.calc._calibrate_total_score(45, team_score=0, opp_score=2), 32)
        # Draw cap
        self.assertEqual(self.calc._calibrate_total_score(43, team_score=2, opp_score=2), 38)

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
