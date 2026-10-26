"""
Unit and integration tests for scripts/update_matchweek.py.
Validates the weekly 2-stage update flow across SQLite and ChromaDB.
"""

import unittest
import tempfile
from pathlib import Path
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from pipeline.db import init_db
from pipeline.models import (
    MatchModel,
    TeamMatchStatsModel,
    MatchReviewModel,
    MatchBundleModel,
)
from pipeline.indexer import MatchIndexer
from pipeline.vector_indexer import TacticalVectorIndexer
from scripts.update_matchweek import MatchweekUpdater


class UpdaterTestEmbeddingFunction(EmbeddingFunction):
    """Deterministic fast test embedding function."""

    def __init__(self):
        super().__init__()

    def name(self) -> str:
        return "updater_test"

    def get_config(self) -> dict:
        return {}

    def __call__(self, input: Documents) -> Embeddings:
        return [[float(len(t)), float(ord(t[0])) if t else 0.0] for t in input]


class TestMatchweekUpdater(unittest.TestCase):
    """Test suite for MatchweekUpdater 2-stage pipeline."""

    def setUp(self):
        # In-memory SQLite
        self.conn = init_db(":memory:")
        self.indexer = MatchIndexer(conn=self.conn)

        # In-memory ChromaDB
        self.chroma_client = chromadb.Client()
        self.vector_indexer = TacticalVectorIndexer(
            collection_name="test_matchweek_updater",
            client=self.chroma_client,
            embedding_function=UpdaterTestEmbeddingFunction(),
        )

        self.updater = MatchweekUpdater(
            indexer=self.indexer,
            vector_indexer=self.vector_indexer,
        )

    def tearDown(self):
        self.updater.close()
        self.indexer.close()
        if self.conn:
            self.conn.close()
        try:
            self.chroma_client.delete_collection("test_matchweek_updater")
        except Exception:
            pass

    def test_update_match_bundle_stage1_and_stage2(self):
        """Verify Stage 1 flash insert followed by Stage 2 confirmed upsert."""
        match_id = "20261021_FCT_KAS"

        # Stage 1: Match Day Flash (Basic score + official report)
        bundle_stage1 = MatchBundleModel(
            match=MatchModel(
                match_id=match_id,
                season=2026,
                matchweek=28,
                date="2026-10-21",
                home_team_id="FCT",
                away_team_id="KAS",
                home_score=2,
                away_score=1,
            ),
            team_stats=[
                TeamMatchStatsModel(
                    match_id=match_id,
                    team_id="FCT",
                    possession=55.0,
                    xg=1.85,
                    shots=12,
                ),
            ],
            reviews=[
                MatchReviewModel(
                    match_id=match_id,
                    review_type="OFFICIAL_REPORT",
                    content_text="FC東京が2-1で勝利。",
                ),
            ],
        )

        res1 = self.updater.update_match_bundle(bundle_stage1, stage=1)
        self.assertEqual(res1["stage"], 1)
        self.assertEqual(res1["chunks_indexed"], 4)
        self.assertEqual(self.vector_indexer.count(), 4)

        # Verify Stage in SQLite
        cursor = self.conn.cursor()
        cursor.execute("SELECT source_updated_stage, home_score FROM matches WHERE match_id = ?", (match_id,))
        row = cursor.fetchone()
        self.assertEqual(row["source_updated_stage"], 1)
        self.assertEqual(row["home_score"], 2)

        # Stage 2: Confirmed tracking and stats update
        bundle_stage2 = MatchBundleModel(
            match=MatchModel(
                match_id=match_id,
                season=2026,
                matchweek=28,
                date="2026-10-21",
                home_team_id="FCT",
                away_team_id="KAS",
                home_score=2,
                away_score=1,
            ),
            team_stats=[
                TeamMatchStatsModel(
                    match_id=match_id,
                    team_id="FCT",
                    possession=55.0,
                    xg=1.85,
                    shots=12,
                    total_distance_km=114.5,
                    sprints=160,
                ),
            ],
            reviews=[
                MatchReviewModel(
                    match_id=match_id,
                    review_type="OFFICIAL_REPORT",
                    content_text="FC東京が2-1で勝利。総走行距離114.5km。",
                ),
            ],
        )

        res2 = self.updater.update_match_bundle(bundle_stage2, stage=2)
        self.assertEqual(res2["stage"], 2)
        # ChromaDB chunk count should remain 4 due to idempotent upsert
        self.assertEqual(self.vector_indexer.count(), 4)

        cursor.execute("SELECT source_updated_stage FROM matches WHERE match_id = ?", (match_id,))
        row2 = cursor.fetchone()
        self.assertEqual(row2["source_updated_stage"], 2)

        cursor.execute("SELECT total_distance_km, sprints FROM team_match_stats WHERE match_id = ? AND team_id = 'FCT'", (match_id,))
        stats_row = cursor.fetchone()
        self.assertEqual(stats_row["total_distance_km"], 114.5)
        self.assertEqual(stats_row["sprints"], 160)

    def test_update_from_markdown_file(self):
        """Verify update execution from a markdown report file."""
        sample_markdown = """# 試合レポート: 2026明治安田J1 第34節 FC東京 vs 水戸ホーリーホック

## 1. 試合基本情報
- **開催日時**: 2026/10/25 (日) 14:03キックオフ
- **スタジアム**: 味の素スタジアム
- **入場者数**: 28,452人
- **天候・気候**: 晴 / 19.2℃ / 48%
- **試合結果**: FC東京 6 - 0 水戸
- **得点経過**: 仲川 輝人 32'

## 2. チームスタッツサマリー
| スタッツ項目 | FC東京 | 水戸 |
| :--- | :--- | :--- |
| ボール支配率 | 62% | 38% |
| シュート数 | 18 | 4 |

## 5. 公式マッチサマリー
FC東京が水戸に大勝。
"""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
            f.write(sample_markdown)
            temp_path = f.name

        try:
            res = self.updater.update_from_markdown_file(temp_path, stage=1)
            self.assertEqual(res["score"], "6-0")
            self.assertEqual(res["chunks_indexed"], 4)
            self.assertEqual(self.vector_indexer.count(), 4)
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
