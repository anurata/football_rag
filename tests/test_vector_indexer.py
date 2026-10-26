"""
Unit and integration tests for pipeline/vector_indexer.py.
Validates ChromaDB 4-chunk indexing, idempotence, metadata filtering, and queries.
"""

import unittest
from typing import List
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    MatchBundleModel,
)
from pipeline.vector_indexer import TacticalVectorIndexer


class DeterministicTestEmbeddingFunction(EmbeddingFunction):
    """Fast, deterministic in-memory embedding function for reproducible unit tests."""

    def __init__(self):
        super().__init__()

    def name(self) -> str:
        return "deterministic_test"

    def get_config(self) -> dict:
        return {}

    def __call__(self, input: Documents) -> Embeddings:


        embeddings = []
        for text in input:
            # Simple pseudo-embedding based on string length and ascii codes
            length = float(len(text))
            first_char = float(ord(text[0])) if text else 0.0
            vec = [length, first_char, length * 0.5, first_char * 0.2]
            embeddings.append(vec)
        return embeddings


class TestTacticalVectorIndexer(unittest.TestCase):
    """Test suite for TacticalVectorIndexer operations using in-memory ChromaDB."""

    def setUp(self):
        self.chroma_client = chromadb.Client()
        self.embedding_fn = DeterministicTestEmbeddingFunction()
        self.indexer = TacticalVectorIndexer(
            collection_name="test_tactical_fact",
            client=self.chroma_client,
            embedding_function=self.embedding_fn,
        )

    def tearDown(self):
        try:
            self.chroma_client.delete_collection("test_tactical_fact")
        except Exception:
            pass

    def _build_sample_bundle(
        self,
        match_id: str = "20261021_FCT_KAS",
        home_team: str = "FCT",
        away_team: str = "KAS",
    ) -> MatchBundleModel:
        """Helper to create test bundle with adjustable match IDs."""
        match = MatchModel(
            match_id=match_id,
            season=2026,
            matchweek=34,
            date="2026-10-21",
            home_team_id=home_team,
            away_team_id=away_team,
            home_score=2,
            away_score=1,
            stadium="味の素スタジアム",
        )

        team_stats = [
            TeamMatchStatsModel(
                match_id=match_id,
                team_id=home_team,
                period="ALL",
                possession=54.0,
                xg=2.1,
                shots=14,
            ),
            TeamMatchStatsModel(
                match_id=match_id,
                team_id=away_team,
                period="ALL",
                possession=46.0,
                xg=1.1,
                shots=8,
            ),
        ]

        player_stats = [
            PlayerMatchStatsModel(
                match_id=match_id,
                player_name="小泉 慶",
                team_id=home_team,
                is_starter=True,
                avg_x=52.0,
                avg_y=48.0,
            ),
        ]

        events = [
            MatchEventModel(
                event_id=f"EV_{match_id}_01",
                match_id=match_id,
                minute=25,
                period="1H",
                team_id=home_team,
                event_type="GOAL",
                coord_x=90.0,
                coord_y=50.0,
                xg=0.55,
                description_text="中央バイタルからの鮮やかなミドルシュート",
            ),
        ]

        reviews = [
            MatchReviewModel(
                match_id=match_id,
                review_type="OFFICIAL_REPORT",
                title="白熱の攻防戦",
                content_text="終始主導権を握ったホームチームが勝利を収めた。",
            ),
            MatchReviewModel(
                match_id=match_id,
                review_type="HOME_COACH",
                speaker_name="クラモフスキー",
                speaker_team_id=home_team,
                title="選手たちのインテンシティを称賛",
                content_text="ハイプレスが機能し、相手のビルドアップを寸断できた。",
            ),
            MatchReviewModel(
                match_id=match_id,
                review_type="HOME_PLAYER",
                speaker_name="小泉 慶",
                speaker_team_id=home_team,
                title="ピッチでの感触",
                content_text="セカンドボールの回収で優位に立てた。",
            ),
        ]

        return MatchBundleModel(
            match=match,
            team_stats=team_stats,
            player_stats=player_stats,
            events=events,
            reviews=reviews,
        )

    def test_upsert_bundle_creates_exact_4_chunks(self):
        """Indexing a match bundle must store exactly 4 chunks with proper IDs."""
        bundle = self._build_sample_bundle()
        created_chunks = self.indexer.upsert_bundle(bundle)

        self.assertEqual(len(created_chunks), 4)
        self.assertEqual(self.indexer.count(), 4)

        expected_chunk_ids = [
            f"{bundle.match.match_id}_match_summary_and_stats",
            f"{bundle.match.match_id}_tactical_timeline_and_zones",
            f"{bundle.match.match_id}_manager_interviews",
            f"{bundle.match.match_id}_player_interviews",
        ]

        for cid in expected_chunk_ids:
            res = self.indexer.collection.get(ids=[cid])
            self.assertEqual(len(res["ids"]), 1)
            self.assertEqual(res["ids"][0], cid)

    def test_idempotent_upsert(self):
        """Repeatedly upserting the same bundle must not duplicate records."""
        bundle = self._build_sample_bundle()

        # First indexing
        self.indexer.upsert_bundle(bundle)
        self.assertEqual(self.indexer.count(), 4)

        # Second indexing of same bundle
        self.indexer.upsert_bundle(bundle)
        self.assertEqual(self.indexer.count(), 4)

    def test_query_with_metadata_filter(self):
        """Querying vector index with metadata filter returns matching chunk types."""
        bundle = self._build_sample_bundle()
        self.indexer.upsert_bundle(bundle)

        # Filter by chunk_type
        results = self.indexer.query(
            query_text="ハイプレス 戦術意図",
            n_results=2,
            where={"chunk_type": "manager_interviews"},
        )

        self.assertGreaterEqual(len(results), 1)
        top_match = results[0]
        self.assertEqual(
            top_match["metadata"]["chunk_type"],
            "manager_interviews",
        )
        self.assertIn("クラモフスキー", top_match["content"])

    def test_get_and_delete_by_match_id(self):
        """Verify retrieval and deletion of chunks by match_id."""
        bundle1 = self._build_sample_bundle("MATCH_01", "FCT", "KAS")
        bundle2 = self._build_sample_bundle("MATCH_02", "YFM", "URW")

        self.indexer.upsert_bundle(bundle1)
        self.indexer.upsert_bundle(bundle2)
        self.assertEqual(self.indexer.count(), 8)

        # Retrieve match 1 chunks
        m1_chunks = self.indexer.get_by_match_id("MATCH_01")
        self.assertEqual(len(m1_chunks), 4)

        # Delete match 1 chunks
        self.indexer.delete_by_match_id("MATCH_01")
        self.assertEqual(self.indexer.count(), 4)

        # Match 2 chunks remain intact
        m2_chunks = self.indexer.get_by_match_id("MATCH_02")
        self.assertEqual(len(m2_chunks), 4)


if __name__ == "__main__":
    unittest.main()
