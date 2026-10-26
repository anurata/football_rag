"""
Unit tests for agent/retriever.py.
Validates Layer 1 fact vector retrieval and Layer 2 tactical YAML knowledge retrieval.
"""

import unittest
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from agent.retriever import TacticalHybridRetriever
from pipeline.vector_indexer import TacticalVectorIndexer
from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    PlayerMatchStatsModel,
    MatchEventModel,
    MatchReviewModel,
    MatchBundleModel,
)


class TestEmbeddingFunction(EmbeddingFunction):
    """Deterministic fast test embedding function."""

    def __init__(self):
        super().__init__()

    def name(self) -> str:
        return "retriever_test"

    def get_config(self) -> dict:
        return {}

    def __call__(self, input: Documents) -> Embeddings:
        return [[float(len(t)), float(ord(t[0])) if t else 0.0] for t in input]


class TestTacticalHybridRetriever(unittest.TestCase):
    """Test suite for 2-layer tactical hybrid retriever."""

    def setUp(self):
        self.chroma_client = chromadb.Client()
        self.vector_indexer = TacticalVectorIndexer(
            collection_name="test_hybrid_retriever",
            client=self.chroma_client,
            embedding_function=TestEmbeddingFunction(),
        )
        self.retriever = TacticalHybridRetriever(vector_indexer=self.vector_indexer)
        self._seed_sample_fact()

    def tearDown(self):
        try:
            self.chroma_client.delete_collection("test_hybrid_retriever")
        except Exception:
            pass

    def _seed_sample_fact(self):
        """Seed a sample match bundle into the in-memory vector index."""
        match = MatchModel(
            match_id="20261021_FCT_KAS",
            season=2026,
            matchweek=28,
            date="2026-10-21",
            home_team_id="FCT",
            away_team_id="KAS",
            home_score=2,
            away_score=1,
            stadium="味スタ",
        )
        stats = [
            TeamMatchStatsModel(
                match_id="20261021_FCT_KAS",
                team_id="FCT",
                possession=55.0,
                xg=1.85,
                shots=12,
            ),
            TeamMatchStatsModel(
                match_id="20261021_FCT_KAS",
                team_id="KAS",
                possession=45.0,
                xg=0.92,
                shots=8,
            ),
        ]
        reviews = [
            MatchReviewModel(
                match_id="20261021_FCT_KAS",
                review_type="OFFICIAL_REPORT",
                title="FC東京が鹿島に競り勝つ",
                content_text="前半から激しいプレス合戦となり、FC東京が先制。",
            ),
            MatchReviewModel(
                match_id="20261021_FCT_KAS",
                review_type="HOME_COACH",
                speaker_name="クラモフスキー監督",
                speaker_team_id="FCT",
                content_text="選手たちが90分間規律を守ってハイプレスを継続できた。",
            ),
        ]
        bundle = MatchBundleModel(
            match=match,
            team_stats=stats,
            player_stats=[],
            events=[],
            reviews=reviews,
        )
        self.vector_indexer.upsert_bundle(bundle)

    def test_knowledge_base_loaded(self):
        """Verify YAML knowledge bases loaded properly from disk."""
        self.assertTrue(len(self.retriever.causal_trees) > 0)
        self.assertTrue(len(self.retriever.tactical_tradeoffs) > 0)
        self.assertTrue(len(self.retriever.system_matrix) > 0)

    def test_search_fact_chunks(self):
        """Verify Layer 1 ChromaDB retrieval with match_id and chunk_type filters."""
        results = self.retriever.search_fact_chunks(
            query="ハイプレス",
            match_id="20261021_FCT_KAS",
            n_results=2,
        )
        self.assertTrue(len(results) > 0)
        for r in results:
            self.assertEqual(r["metadata"]["match_id"], "20261021_FCT_KAS")

    def test_search_causal_hypotheses(self):
        """Verify Layer 2 causal tree retrieval for metric fluctuations."""
        trees = self.retriever.search_causal_hypotheses("パス成功率")
        self.assertTrue(len(trees) > 0)
        target = trees[0]
        self.assertIn("hypotheses", target)
        self.assertTrue(len(target["hypotheses"]) >= 2)

    def test_search_tactical_tradeoffs(self):
        """Verify Layer 2 tactical tradeoff retrieval (main effects vs side effects)."""
        tradeoffs = self.retriever.search_tactical_tradeoffs("ハイライン")
        self.assertTrue(len(tradeoffs) > 0)
        t = tradeoffs[0]
        self.assertIn("main_effects", t)
        self.assertIn("side_effects", t)

    def test_get_system_matchup_forward_and_reverse(self):
        """Verify formation matchup dynamics (4-4-2 vs 3-4-2-1) in both directions."""
        matchup_ab = self.retriever.get_system_matchup("4-4-2", "3-4-2-1")
        self.assertIsNotNone(matchup_ab)
        self.assertTrue(len(matchup_ab["advantages_for_a"]) > 0)
        self.assertTrue(len(matchup_ab["advantages_for_b"]) > 0)
        self.assertTrue(len(matchup_ab["pinning_mechanisms"]) > 0)

        # Reverse lookup (3-4-2-1 vs 4-4-2)
        matchup_ba = self.retriever.get_system_matchup("3-4-2-1", "4-4-2")
        self.assertIsNotNone(matchup_ba)
        # For BA, advantages_for_a should correspond to 3-4-2-1
        self.assertEqual(
            matchup_ab["advantages_for_a"],
            matchup_ba["advantages_for_b"],
        )

    def test_retrieve_tactical_context_combined(self):
        """Verify assembled multi-layer context for analyst agent prompt."""
        context = self.retriever.retrieve_tactical_context(
            query="ハイプレスと背後のスペース",
            match_id="20261021_FCT_KAS",
            team_id="FCT",
            formation_a="4-4-2",
            formation_b="3-4-2-1",
        )
        self.assertIn("query", context)
        self.assertIn("fact_chunks", context)
        self.assertIn("causal_hypotheses", context)
        self.assertIn("tactical_tradeoffs", context)
        self.assertIn("system_matchup", context)
        self.assertIsNotNone(context["system_matchup"])


if __name__ == "__main__":
    unittest.main()
