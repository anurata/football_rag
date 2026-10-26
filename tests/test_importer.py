"""
Unit and integration tests for markdown parsing and database importing.
"""

import os
import unittest
from pipeline.db import init_db
from pipeline.indexer import MatchIndexer
from pipeline.normalizer import EntityNormalizer
from pipeline.importer import parse_jleague_markdown, import_markdown_file


class TestMarkdownImporter(unittest.TestCase):
    """Test parsing markdown records and importing them into SQLite."""

    @classmethod
    def setUpClass(cls):
        cls.normalizer = EntityNormalizer()
        cls.sample_path = os.path.join(
            "data",
            "markdown",
            "20261025_FCT_MIT.md",
        )

    def test_parse_jleague_markdown(self):
        """Verify markdown extraction accurately populates MatchBundleModel."""
        with open(self.sample_path, "r", encoding="utf-8") as f:
            content = f.read()

        bundle = parse_jleague_markdown(content, self.normalizer)

        # Match check
        self.assertEqual(bundle.match.match_id, "20261025_FCT_MIT")
        self.assertEqual(bundle.match.home_team_id, "FCT")
        self.assertEqual(bundle.match.away_team_id, "MIT")
        self.assertEqual(bundle.match.home_score, 6)
        self.assertEqual(bundle.match.away_score, 0)
        self.assertEqual(bundle.match.attendance, 23602)
        self.assertIn("味の素スタジアム", bundle.match.stadium)

        # Team stats check
        self.assertEqual(len(bundle.team_stats), 2)
        home_s = next(s for s in bundle.team_stats if s.team_id == "FCT")
        away_s = next(s for s in bundle.team_stats if s.team_id == "MIT")
        self.assertEqual(home_s.shots, 23)
        self.assertEqual(home_s.shots_on_target, 11)
        self.assertAlmostEqual(home_s.possession, 55.0)
        self.assertAlmostEqual(home_s.total_distance_km, 116.9)
        self.assertEqual(home_s.sprints, 166)

        self.assertEqual(away_s.shots, 12)
        self.assertEqual(away_s.shots_on_target, 2)
        self.assertAlmostEqual(away_s.possession, 45.0)

        # Goal events check (6 goals)
        self.assertEqual(len(bundle.events), 6)
        self.assertEqual(bundle.events[0].player_name, "仲川 輝人")
        self.assertEqual(bundle.events[0].minute, 32)
        self.assertEqual(bundle.events[0].event_type, "GOAL")

        # Reviews check (1 report + 2 coaches + 4 players = 7 total)
        self.assertEqual(len(bundle.reviews), 7)
        rep = next(r for r in bundle.reviews if r.review_type == "OFFICIAL_REPORT")
        self.assertIn("雨がちらつく日曜日", rep.content_text)

        c_tokyo = next(r for r in bundle.reviews if r.review_type == "HOME_COACH")
        self.assertEqual(c_tokyo.speaker_name, "松橋 力蔵")

        c_mito = next(r for r in bundle.reviews if r.review_type == "AWAY_COACH")
        self.assertEqual(c_mito.speaker_name, "樹森 大介")

        players = [r.speaker_name for r in bundle.reviews if "PLAYER" in r.review_type]
        self.assertEqual(len(players), 4)
        self.assertIn("ダニ ゴメス", players)
        self.assertIn("安斎 颯馬", players)
        self.assertIn("キム スンギュ", players)
        self.assertIn("木本 恭生", players)

    def test_import_markdown_file_to_db(self):
        """Test end-to-end import into database and verify SQL query capabilities."""
        conn = init_db(":memory:")
        indexer = MatchIndexer(conn=conn)

        bundle = import_markdown_file(
            self.sample_path,
            indexer,
            self.normalizer,
        )
        self.assertIsNotNone(bundle)

        cursor = conn.cursor()

        # Query matches
        cursor.execute("SELECT * FROM matches WHERE match_id = '20261025_FCT_MIT'")
        m_row = cursor.fetchone()
        self.assertIsNotNone(m_row)
        self.assertEqual(m_row["home_score"], 6)

        # Query goal events joined with match info
        query = """
        SELECT e.minute, e.player_name, m.home_score, m.away_score
        FROM match_events e
        JOIN matches m ON e.match_id = m.match_id
        WHERE e.event_type = 'GOAL'
        ORDER BY e.minute ASC;
        """
        cursor.execute(query)
        goals = cursor.fetchall()
        self.assertEqual(len(goals), 6)
        self.assertEqual(goals[0]["minute"], 32)
        self.assertEqual(goals[0]["player_name"], "仲川 輝人")

        indexer.close()
        conn.close()


if __name__ == "__main__":
    unittest.main()
