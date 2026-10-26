"""
Unit tests for pipeline/indexer.py SQLite persistence and idempotence.
"""

import unittest
from pipeline.db import init_db
from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    MatchBundleModel,
)
from pipeline.indexer import MatchIndexer


class TestMatchIndexer(unittest.TestCase):
    """Test inserting, updating, and querying match bundles in SQLite."""

    def setUp(self):
        self.conn = init_db(":memory:")
        self.indexer = MatchIndexer(conn=self.conn)

    def tearDown(self):
        self.indexer.close()
        self.conn.close()

    def _create_sample_bundle(
        self,
        match_id: str = "20261021_FCT_KAS",
        stage: int = 1,
        total_dist: float = None,
    ) -> MatchBundleModel:
        """Helper to create test bundle with adjustable parameters."""
        match = MatchModel(
            match_id=match_id,
            season=2026,
            matchweek=34,
            date="2026-10-21",
            home_team_id="FCT",
            away_team_id="KAS",
            home_score=2,
            away_score=1,
            stadium="味の素スタジアム",
            weather="晴",
            source_updated_stage=stage,
        )

        team_stats = [
            TeamMatchStatsModel(
                match_id=match_id,
                team_id="FCT",
                period="ALL",
                possession=52.0,
                xg=1.85,
                shots=14,
                total_distance_km=total_dist,
            ),
            TeamMatchStatsModel(
                match_id=match_id,
                team_id="KAS",
                period="ALL",
                possession=48.0,
                xg=1.12,
                shots=9,
                total_distance_km=total_dist,
            ),
        ]

        player_stats = [
            PlayerMatchStatsModel(
                match_id=match_id,
                player_id="P_FCT_KOIZUMI",
                player_name="小泉 慶",
                team_id="FCT",
                is_starter=True,
                minutes_played=90,
                position="MF",
                number=37,
                goals=0,
                distance_km=11.8 if stage == 2 else None,
            ),
        ]

        events = [
            MatchEventModel(
                event_id=f"EV_{match_id}_01",
                match_id=match_id,
                minute=34,
                period="1H",
                game_state="DRAW",
                team_id="FCT",
                player_name="ディエゴ オリヴェイラ",
                event_type="GOAL",
                coord_x=92.5,
                coord_y=51.0,
                zone_name="ボックス内・ゴール前",
                xg=0.45,
                description_text="左からのグラウンダークロスを押し込む。",
            ),
        ]

        reviews = [
            MatchReviewModel(
                match_id=match_id,
                review_type="HOME_COACH",
                speaker_name="ピーター クラモフスキー",
                speaker_team_id="FCT",
                title="監督記者会見",
                content_text="選手たちがアグレッシブにプレスをかけてくれた。",
            ),
        ]

        return MatchBundleModel(
            match=match,
            team_stats=team_stats,
            player_stats=player_stats,
            events=events,
            reviews=reviews,
        )

    def test_upsert_bundle_basic(self):
        """Verify complete bundle insertion."""
        bundle = self._create_sample_bundle()
        self.indexer.upsert_bundle(bundle)

        cursor = self.conn.cursor()

        # Check match
        cursor.execute("SELECT * FROM matches WHERE match_id = ?", (bundle.match.match_id,))
        m_row = cursor.fetchone()
        self.assertIsNotNone(m_row)
        self.assertEqual(m_row["home_score"], 2)

        # Check team stats
        cursor.execute("SELECT COUNT(*) FROM team_match_stats WHERE match_id = ?", (bundle.match.match_id,))
        self.assertEqual(cursor.fetchone()[0], 2)

        # Check player stats
        cursor.execute("SELECT * FROM player_match_stats WHERE player_name = '小泉 慶'")
        p_row = cursor.fetchone()
        self.assertIsNotNone(p_row)
        self.assertEqual(p_row["team_id"], "FCT")

        # Check events
        cursor.execute("SELECT * FROM match_events WHERE event_type = 'GOAL'")
        e_row = cursor.fetchone()
        self.assertIsNotNone(e_row)
        self.assertEqual(e_row["minute"], 34)

        # Check reviews
        cursor.execute("SELECT * FROM match_reviews WHERE review_type = 'HOME_COACH'")
        r_row = cursor.fetchone()
        self.assertIsNotNone(r_row)
        self.assertIn("アグレッシブ", r_row["content_text"])

    def test_upsert_idempotence(self):
        """Verify calling upsert multiple times updates instead of duplicating rows."""
        bundle = self._create_sample_bundle()
        self.indexer.upsert_bundle(bundle)
        self.indexer.upsert_bundle(bundle)

        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM matches")
        self.assertEqual(cursor.fetchone()[0], 1)

        cursor.execute("SELECT COUNT(*) FROM team_match_stats")
        self.assertEqual(cursor.fetchone()[0], 2)

        cursor.execute("SELECT COUNT(*) FROM match_events")
        self.assertEqual(cursor.fetchone()[0], 1)

        cursor.execute("SELECT COUNT(*) FROM match_reviews")
        self.assertEqual(cursor.fetchone()[0], 1)

    def test_stage2_tracking_upsert(self):
        """Verify stage 2 upsert merges tracking stats without losing stage 1 data."""
        # Stage 1: Initial upload without distance
        bundle_s1 = self._create_sample_bundle(stage=1, total_dist=None)
        self.indexer.upsert_bundle(bundle_s1)

        cursor = self.conn.cursor()
        cursor.execute("SELECT total_distance_km FROM team_match_stats WHERE team_id = 'FCT'")
        self.assertIsNone(cursor.fetchone()[0])

        # Stage 2: Confirmed tracking data added
        bundle_s2 = self._create_sample_bundle(stage=2, total_dist=114.5)
        self.indexer.upsert_bundle(bundle_s2)

        cursor.execute("SELECT total_distance_km, xg FROM team_match_stats WHERE team_id = 'FCT'")
        updated_stat = cursor.fetchone()
        self.assertAlmostEqual(updated_stat["total_distance_km"], 114.5)
        self.assertAlmostEqual(updated_stat["xg"], 1.85)

        cursor.execute("SELECT source_updated_stage FROM matches WHERE match_id = '20261021_FCT_KAS'")
        self.assertEqual(cursor.fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
