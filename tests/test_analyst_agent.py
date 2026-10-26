"""
Unit and integration tests for agent/engine.py and agent/analyst_prompts.py.
Validates the end-to-end prompt preparation, context injection, and analysis execution.
"""

import unittest
import sqlite3
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

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
from pipeline.vector_indexer import TacticalVectorIndexer
from agent.sql_tools import TacticalSQLTools
from agent.retriever import TacticalHybridRetriever
from agent.engine import TacticalAnalystEngine
from agent.analyst_prompts import SYSTEM_PROMPT, WATCHING_LENSES_GUIDE


class AgentTestEmbeddingFunction(EmbeddingFunction):
    """Deterministic fast test embedding function."""

    def __init__(self):
        super().__init__()

    def name(self) -> str:
        return "agent_test"

    def get_config(self) -> dict:
        return {}

    def __call__(self, input: Documents) -> Embeddings:
        return [[float(len(t)), float(ord(t[0])) if t else 0.0] for t in input]


class TestTacticalAnalystAgent(unittest.TestCase):
    """Test suite for TacticalAnalystEngine prompt generation and execution."""

    def setUp(self):
        # 1. In-memory SQLite DB
        self.conn = init_db(":memory:")
        self.indexer = MatchIndexer(conn=self.conn)
        self.sql_tools = TacticalSQLTools(conn=self.conn)

        # 2. In-memory ChromaDB
        self.chroma_client = chromadb.Client()
        self.vector_indexer = TacticalVectorIndexer(
            collection_name="test_agent_engine",
            client=self.chroma_client,
            embedding_function=AgentTestEmbeddingFunction(),
        )
        self.retriever = TacticalHybridRetriever(vector_indexer=self.vector_indexer)

        # 3. Reasoning Engine
        self.engine = TacticalAnalystEngine(
            sql_tools=self.sql_tools,
            retriever=self.retriever,
        )

        self._seed_sample_data()

    def tearDown(self):
        self.sql_tools.close()
        self.indexer.close()
        if self.conn:
            self.conn.close()
        try:
            self.chroma_client.delete_collection("test_agent_engine")
        except Exception:
            pass

    def _seed_sample_data(self):
        """Seed rich match bundle into SQLite and ChromaDB."""
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
                period="ALL",
                game_state="ALL",
                possession=55.0,
                xg=1.85,
                shots=12,
                total_distance_km=114.2,
                sprints=150,
            ),
            TeamMatchStatsModel(
                match_id="20261021_FCT_KAS",
                team_id="FCT",
                period="ALL",
                game_state="LEADING",
                possession=48.0,
                xg=0.65,
                shots=4,
            ),
            TeamMatchStatsModel(
                match_id="20261021_FCT_KAS",
                team_id="KAS",
                period="ALL",
                game_state="ALL",
                possession=45.0,
                xg=0.92,
                shots=8,
            ),
        ]
        players = [
            PlayerMatchStatsModel(
                match_id="20261021_FCT_KAS",
                player_id="p_koki",
                player_name="小泉 慶",
                team_id="FCT",
                is_starter=True,
                minutes_played=90,
                position="MF",
                avg_x=52.0,
                avg_y=48.0,
            ),
            PlayerMatchStatsModel(
                match_id="20261021_FCT_KAS",
                player_id="p_ryotaro",
                player_name="荒木 遼太郎",
                team_id="FCT",
                is_starter=True,
                minutes_played=75,
                position="MF",
                avg_x=68.0,
                avg_y=40.0,
            ),
        ]
        events = [
            MatchEventModel(
                event_id="e1",
                match_id="20261021_FCT_KAS",
                minute=25,
                period="1H",
                game_state="DRAW",
                team_id="FCT",
                player_name="荒木 遼太郎",
                event_type="GOAL",
                xg=0.65,
                description_text="先制ゴール",
            ),
        ]
        reviews = [
            MatchReviewModel(
                match_id="20261021_FCT_KAS",
                review_type="OFFICIAL_REPORT",
                title="FC東京が鹿島に競り勝つ",
                content_text="FC東京が強度の高いハイプレスで鹿島のビルドアップを寸断。",
            ),
        ]

        bundle = MatchBundleModel(
            match=match,
            team_stats=stats,
            player_stats=players,
            events=events,
            reviews=reviews,
        )

        self.indexer.upsert_bundle(bundle)
        self.vector_indexer.upsert_bundle(bundle)

    def test_build_why_analysis(self):
        """Verify Question 1: Why causal prompt assembly with elimination requirement."""
        result = self.engine.build_why_analysis(
            match_id="20261021_FCT_KAS",
            team_id="FCT",
            phenomenon="敵陣でのパス成功率低下とロスト増加",
            metric_keyword="パス成功率",
        )
        self.assertIn("system_prompt", result)
        self.assertIn("user_prompt", result)
        user_p = result["user_prompt"]
        self.assertIn("消去法で真因を特定", user_p)
        self.assertIn("敵陣でのパス成功率低下とロスト増加", user_p)
        self.assertIn("仮説", user_p)

    def test_build_how_analysis(self):
        """Verify Question 2: How prescription prompt with structural & individual solutions."""
        result = self.engine.build_how_analysis(
            team_id="FCT",
            bottleneck="ハイプレス突破後のDFライン背後被弾",
            tradeoff_keyword="ハイライン",
            formation_a="4-4-2",
            formation_b="3-4-2-1",
        )
        user_p = result["user_prompt"]
        self.assertIn("構造的解決策", user_p)
        self.assertIn("属人的解決策", user_p)
        self.assertIn("副作用と対策", user_p)
        self.assertIsNotNone(result["context_data"]["system_matchup"])

    def test_build_what_if_analysis(self):
        """Verify Question 3: What-if prompt with main scenario vs risk scenario."""
        result = self.engine.build_what_if_analysis(
            opponent_team_id="KAS",
            tactical_change="SBをインサイドに絞らせる偽SB化",
            tradeoff_keyword="偽SB",
            formation_a="4-4-2",
            formation_b="3-4-2-1",
        )
        user_p = result["user_prompt"]
        self.assertIn("メインシナリオ（光）", user_p)
        self.assertIn("リスクシナリオ（影）", user_p)
        self.assertIn("成否の分岐点", user_p)

    def test_build_unsung_hero_analysis(self):
        """Verify Question 5: Unsung hero On/Off analysis."""
        result = self.engine.build_unsung_hero_analysis(
            team_id="FCT",
            player_name="小泉 慶",
        )
        user_p = result["user_prompt"]
        self.assertIn("小泉 慶", user_p)
        self.assertIn("on_field", user_p)

    def test_build_chemistry_analysis(self):
        """Verify Question 6: Pairing chemistry analysis."""
        result = self.engine.build_chemistry_analysis(
            team_id="FCT",
            player_a="小泉 慶",
            player_b="荒木 遼太郎",
        )
        user_p = result["user_prompt"]
        self.assertIn("co_starts", user_p)
        self.assertIn("avg_distance", user_p)

    def test_build_game_state_dna_analysis(self):
        """Verify Question 7: Game state DNA analysis."""
        result = self.engine.build_game_state_dna_analysis(
            team_id="FCT",
            match_id="20261021_FCT_KAS",
        )
        user_p = result["user_prompt"]
        self.assertIn("LEADING", user_p)

    def test_build_watching_guide(self):
        """Verify 4 Watching Perspectives / Lenses generation prompt."""
        result = self.engine.build_watching_guide(
            match_id="20261021_FCT_KAS",
            formation_home="4-4-2",
            formation_away="3-4-2-1",
        )
        user_p = result["user_prompt"]
        self.assertIn("開始10分の「配置の答え合わせ」", user_p)
        self.assertIn("守備のスイッチが入る「トリガー」の瞬間", user_p)
        self.assertIn("炭鉱のカナリア", user_p)
        self.assertIn("ベンチのチェス", user_p)

    def test_run_analysis_with_mock_llm(self):
        """Verify end-to-end execution flow with a mock LLM callable."""
        context = self.engine.build_why_analysis(
            match_id="20261021_FCT_KAS",
            team_id="FCT",
            phenomenon="敵陣パス成功率低下",
        )

        def mock_llm(sys_prompt: str, user_prompt: str) -> str:
            self.assertIn("Jリーグのトッププロ戦術分析官", sys_prompt)
            self.assertIn("消去法で真因を特定", user_prompt)
            return "【分析結果】H1とH2を検証した結果、相手のプレス強度が真因と特定。"

        execution_output = self.engine.run_analysis(
            analysis_context=context,
            llm_callable=mock_llm,
        )

        self.assertIsNotNone(execution_output["response"])
        self.assertIn("真因と特定", execution_output["response"])


if __name__ == "__main__":
    unittest.main()
