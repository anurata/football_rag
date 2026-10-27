"""Integration test for FC Tokyo 15-Perspective Tactical Reports (tests/test_fct_15_perspectives.py).

Validates that all 12 FC Tokyo matches generate rich 15-perspective reports
including Layer 1 (Data), Layer 2 (Events), Layer 3 (Theory), and AWAY perspective.
"""

import unittest
from agent.objective_profiler import MatchObjectiveProfiler
from pipeline.db import get_db_connection
from scripts.fetch_fct_canonical import FCT_CANONICAL_MATCHES


class TestFCT15Perspectives(unittest.TestCase):
    """FC東京全12試合の15観点レポート生成テストスイート."""

    def setUp(self) -> None:
        self.profiler = MatchObjectiveProfiler()

    def test_all_12_matches_generate_complete_15_perspectives(self) -> None:
        """全12試合において15観点および4要素（数値・速報・理論・AWAY）が完全に出力されることを検証する."""
        conn = get_db_connection()
        cursor = conn.cursor()

        for m in FCT_CANONICAL_MATCHES:
            match_id = m["match_id"]
            with self.subTest(match_id=match_id):
                cursor.execute(
                    """
                    SELECT match_id, home_team_id, away_team_id, home_score, away_score, date, matchweek
                    FROM matches
                    WHERE match_id = ?
                    """,
                    (match_id,),
                )
                row = cursor.fetchone()
                self.assertIsNotNone(row, f"Match {match_id} not found in DB")

                summary = {
                    "match": dict(row),
                    "team_stats": {
                        m["home"]: {"possession": 50.0, "shots": 10},
                        m["away"]: {"possession": 50.0, "shots": 10},
                    },
                    "events": [],
                }

                report = self.profiler.build_15_perspective_report(summary)

                # 1. 全体構造サマリー
                overall = report.get("overall_structure_summary")
                self.assertIsNotNone(overall)
                self.assertIn("narrative", overall)
                self.assertIn("phases", overall)

                # 2. 15観点リスト
                perspectives = report.get("perspectives", [])
                self.assertEqual(
                    len(perspectives),
                    15,
                    f"{match_id}: 観点数が15個ではありません (実際: {len(perspectives)})",
                )

                # 3. 4要素の検査
                for p in perspectives:
                    self.assertIn("name", p)
                    self.assertIn("layer1_summary", p)
                    self.assertIn("layer2_counts", p)
                    self.assertIn("layer3_theory", p)
                    self.assertIn("away_perspective", p)

        conn.close()


if __name__ == "__main__":
    unittest.main()
