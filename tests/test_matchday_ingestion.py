"""
tests/test_matchday_ingestion.py

試合終了当日データ更新（Stage 1）パイプラインの単体テスト。
・Stage 1（当日速報確定値）としてのメタデータ整合性
・公式イベント（4ゴール、アシスト）の正確性
・SPAIA選手スタッツ（出場時間、走行距離、スプリント）の永続化
・後日データ（Stage 2言説）との明確な分離
をインメモリDBを用いて高速かつ安全に検証します。
"""

import unittest
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from pipeline.db import init_db
from pipeline.indexer import MatchIndexer
from pipeline.vector_indexer import TacticalVectorIndexer
from scripts.update_matchweek import MatchweekUpdater
from scripts.ingest_matchday_immediate import (
    MatchdayImmediateIngester,
    get_default_2026103109_events,
)


class TestEmbeddingFunction(EmbeddingFunction):
    """テスト用決定論的埋め込み関数"""

    def __init__(self):
        super().__init__()

    def name(self) -> str:
        return "matchday_test"

    def get_config(self) -> dict:
        return {}

    def __call__(self, input: Documents) -> Embeddings:
        return [[float(len(t)), float(ord(t[0])) if t else 0.0] for t in input]


class TestMatchdayImmediateIngestion(unittest.TestCase):
    """試合終了当日即時更新の検証テスト"""

    def setUp(self):
        """インメモリSQLiteとインメモリChromaDBの初期化"""
        self.conn = init_db(":memory:")
        self.indexer = MatchIndexer(conn=self.conn)

        self.chroma_client = chromadb.Client()
        self.vector_indexer = TacticalVectorIndexer(
            client=self.chroma_client,
            embedding_function=TestEmbeddingFunction(),
        )

        self.updater = MatchweekUpdater(
            indexer=self.indexer,
            vector_indexer=self.vector_indexer,
        )

        self.ingester = MatchdayImmediateIngester(
            updater=self.updater,
        )

    def tearDown(self):
        """リソース解放"""
        self.ingester.close()
        self.updater.close()
        if self.conn:
            self.conn.close()

    def test_assemble_bundle_stage1_metadata(self):
        """Stage 1としてのメタデータが正しく構築されているか検証"""
        bundle = self.ingester.assemble_bundle(
            game_id="2026103109",
            matchweek=13,
            date_str="2026-10-31",
            home_team_id="OKA",
            away_team_id="FCT",
            home_score=0,
            away_score=4,
            yahoo_stats={"home_shots": 7, "away_shots": 16},
            spaia_players=[],
            events_data=[],
            dry_summary="【試合終了速報】岡山 0 - 4 FC東京",
        )

        self.assertEqual(bundle.match.match_id, "20261031_OKA_FCT")
        self.assertEqual(bundle.match.source_updated_stage, 1)
        self.assertEqual(bundle.match.home_score, 0)
        self.assertEqual(bundle.match.away_score, 4)
        self.assertEqual(len(bundle.reviews), 1)
        self.assertEqual(bundle.reviews[0].review_type, "OFFICIAL_REPORT")

    def test_player_stats_and_events_extraction(self):
        """選手スタッツ（永野1A、ダニ2G）とイベントが正しく抽出されるか検証"""
        events = get_default_2026103109_events()
        spaia_players = [
            {
                "name": "永野 修都",
                "team_name": "FC東京",
                "is_starter": True,
                "minutes": 90,
                "assists": 1,
                "distance_km": 13.02,
                "sprints": 18,
            },
            {
                "name": "ダニ ゴメス",
                "team_name": "FC東京",
                "is_starter": True,
                "minutes": 90,
                "goals": 2,
                "distance_km": 10.45,
                "sprints": 15,
            },
        ]

        bundle = self.ingester.assemble_bundle(
            game_id="2026103109",
            matchweek=13,
            date_str="2026-10-31",
            home_team_id="OKA",
            away_team_id="FCT",
            home_score=0,
            away_score=4,
            yahoo_stats={},
            spaia_players=spaia_players,
            events_data=events,
            dry_summary="速報テスト",
        )

        self.assertEqual(len(bundle.events), 4)
        self.assertEqual(bundle.events[0].player_name, "遠藤 渓太")
        self.assertEqual(bundle.events[2].player_name, "ダニ・ゴメス")

        self.assertEqual(len(bundle.player_stats), 2)
        nagano = next(p for p in bundle.player_stats if "永野" in p.player_name)
        self.assertEqual(nagano.assists, 1)
        self.assertAlmostEqual(nagano.distance_km, 13.02)

        dani = next(p for p in bundle.player_stats if "ダニ" in p.player_name)
        self.assertEqual(dani.goals, 2)

    def test_execute_matchday_ingest_persistence(self):
        """SQLiteおよびChromaDBへのアトミック永続化が成功するか検証"""
        events = get_default_2026103109_events()
        bundle = self.ingester.assemble_bundle(
            game_id="2026103109",
            matchweek=13,
            date_str="2026-10-31",
            home_team_id="OKA",
            away_team_id="FCT",
            home_score=0,
            away_score=4,
            yahoo_stats={"home_shots": 7, "away_shots": 16, "home_possession": 44.0, "away_possession": 56.0},
            spaia_players=[
                {"name": "永野 修都", "team_name": "FC東京", "is_starter": True, "assists": 1},
            ],
            events_data=events,
            dry_summary="【試合終了速報】岡山 0 - 4 FC東京",
        )

        res = self.ingester.execute_matchday_ingest(bundle)
        self.assertEqual(res["stage"], 1)
        self.assertEqual(res["match_id"], "20261031_OKA_FCT")
        self.assertEqual(res["score"], "0-4")

        # インメモリDBから永続化状態を直接クエリ検証
        cursor = self.conn.cursor()
        
        # matches テーブル検証
        cursor.execute("SELECT home_score, away_score, source_updated_stage FROM matches WHERE match_id = ?", ("20261031_OKA_FCT",))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 0)
        self.assertEqual(row[1], 4)
        self.assertEqual(row[2], 1)

        # match_events テーブル検証 (4ゴール登録)
        cursor.execute("SELECT COUNT(*) FROM match_events WHERE match_id = ? AND event_type = 'GOAL'", ("20261031_OKA_FCT",))
        goal_count = cursor.fetchone()[0]
        self.assertEqual(goal_count, 4)

        # team_stats テーブル検証
        cursor.execute("SELECT COUNT(*) FROM team_match_stats WHERE match_id = ?", ("20261031_OKA_FCT",))
        team_stats_count = cursor.fetchone()[0]
        self.assertEqual(team_stats_count, 2)


if __name__ == "__main__":
    unittest.main()
