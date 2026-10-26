"""
Unit and integration tests for scripts/backfill_mw1_to_12.py.
Validates historical batch ingestion and indexing for early-season matches.
"""

import unittest
import tempfile
from pathlib import Path
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from pipeline.db import init_db
from pipeline.indexer import MatchIndexer
from pipeline.vector_indexer import TacticalVectorIndexer
from scripts.backfill_mw1_to_12 import BackfillPipeline


class BackfillTestEmbeddingFunction(EmbeddingFunction):
    """Deterministic fast test embedding function."""

    def __init__(self):
        super().__init__()

    def name(self) -> str:
        return "backfill_test"

    def get_config(self) -> dict:
        return {}

    def __call__(self, input: Documents) -> Embeddings:
        return [[float(len(t)), float(ord(t[0])) if t else 0.0] for t in input]


class TestBackfillPipeline(unittest.TestCase):
    """Test suite for BackfillPipeline historical batch processing."""

    def setUp(self):
        self.conn = init_db(":memory:")
        self.indexer = MatchIndexer(conn=self.conn)
        self.chroma_client = chromadb.Client()
        self.vector_indexer = TacticalVectorIndexer(
            collection_name="test_backfill",
            client=self.chroma_client,
            embedding_function=BackfillTestEmbeddingFunction(),
        )
        self.pipeline = BackfillPipeline(
            indexer=self.indexer,
            vector_indexer=self.vector_indexer,
        )

    def tearDown(self):
        self.pipeline.close()
        self.indexer.close()
        if self.conn:
            self.conn.close()
        try:
            self.chroma_client.delete_collection("test_backfill")
        except Exception:
            pass

    def test_run_backfill_filtered_by_matchweek(self):
        """Verify backfill correctly ingests matches within matchweek range and skips outside."""
        # Create temp dir with 2 match files: MW 5 and MW 15
        with tempfile.TemporaryDirectory() as tmpdir:
            file_mw5 = Path(tmpdir) / "match_mw5.md"
            file_mw15 = Path(tmpdir) / "match_mw15.md"

            content_mw5 = """# ＦＣ東京vs鹿島アントラーズ (Match ID: 20260401_FCT_KAS)
## 【1. 試合概要・基本データ】
- **開催日時**: 2026/04/01 (水) 19:00 KO
- **スタジアム**: 味の素スタジアム
- **試合結果**: 2 - 1
"""
            content_mw15 = """# ＦＣ東京vs川崎フロンターレ (Match ID: 20260601_FCT_KAW)
## 【1. 試合概要・基本データ】
- **開催日時**: 2026/06/01 (水) 19:00 KO
- **スタジアム**: 味の素スタジアム
- **試合結果**: 1 - 1
"""
            file_mw5.write_text(content_mw5, encoding="utf-8")
            file_mw15.write_text(content_mw15, encoding="utf-8")

            # Run backfill for MW 1 to 12
            report = self.pipeline.run_backfill(
                data_dir=tmpdir,
                start_mw=1,
                end_mw=12,
            )

            # Both matches have no explicit MW in header, so unassigned matches are included
            self.assertEqual(report["total_files"], 2)
            self.assertEqual(report["processed"], 2)
            self.assertEqual(self.vector_indexer.count(), 8)

            # Check SQLite
            cursor = self.conn.cursor()
            cursor.execute("SELECT count(*) as cnt FROM matches;")
            self.assertEqual(cursor.fetchone()["cnt"], 2)

    def test_run_backfill_nonexistent_directory(self):
        """Verify graceful handling when target directory does not exist."""
        report = self.pipeline.run_backfill(data_dir="nonexistent/directory")
        self.assertEqual(report["total_files"], 0)
        self.assertEqual(report["processed"], 0)

    def test_run_backfill_with_schedule_map_fallback(self):
        """Verify matchweek is resolved from schedule_map when missing in markdown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = Path(tmpdir) / "match_sample.md"
            fpath.write_text(
                "# 広島vs浦和 (Match ID: 20240223_HIR_URA)\n"
                "## 【1. 試合概要・基本データ】\n"
                "- **開催日時**: 2024/02/23 14:06\n"
                "- **試合結果**: 2 - 0\n",
                encoding="utf-8",
            )
            # Pipeline with schedule map indicating MW 1
            pipeline_with_map = BackfillPipeline(
                indexer=self.indexer,
                vector_indexer=self.vector_indexer,
                schedule_map={"20240223_HIR_URA": 1},
            )
            report = pipeline_with_map.run_backfill(
                data_dir=tmpdir,
                start_mw=1,
                end_mw=1,
            )
            self.assertEqual(report["processed"], 1)
            self.assertEqual(report["matches"][0]["matchweek"], 1)


if __name__ == "__main__":
    unittest.main()
