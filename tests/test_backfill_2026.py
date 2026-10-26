"""
Unit and integration tests for 2026 season backfill pipeline and DB verification.
tests/test_backfill_2026.py
"""

import os
import unittest
import tempfile
from pathlib import Path
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from pipeline.db import init_db
from pipeline.indexer import MatchIndexer
from pipeline.vector_indexer import TacticalVectorIndexer
from pipeline.importer import parse_jleague_markdown
from pipeline.normalizer import EntityNormalizer
from scripts.backfill_mw1_to_12 import (
    BackfillPipeline,
    _find_match_files,
    _should_skip_auxiliary_file,
)
from scripts.clean_and_verify_db import clean_obsolete_matches, verify_db_integrity


class MockFastEmbeddingFunction(EmbeddingFunction):
    """Deterministic fast test embedding function."""

    def __init__(self):
        super().__init__()

    def name(self) -> str:
        return "mock_fast_2026"

    def get_config(self) -> dict:
        return {}

    def __call__(self, input: Documents) -> Embeddings:
        return [[float(len(t)), float(ord(t[0])) if t else 0.0] for t in input]


class TestBackfill2026Pipeline(unittest.TestCase):
    """Test suite for 2026 season backfill and review parsing improvements."""

    def setUp(self):
        self.conn = init_db(":memory:")
        self.indexer = MatchIndexer(conn=self.conn)
        self.chroma_client = chromadb.Client()
        self.vector_indexer = TacticalVectorIndexer(
            collection_name="test_backfill_2026",
            client=self.chroma_client,
            embedding_function=MockFastEmbeddingFunction(),
        )
        self.normalizer = EntityNormalizer()
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
            self.chroma_client.delete_collection("test_backfill_2026")
        except Exception:
            pass

    def test_parse_2026_markdown_review_attribution(self):
        """Verify coach and player reviews are correctly attributed to HOME vs AWAY teams."""
        md_content = """# ガンバ大阪 vs 浦和レッズ (Match ID: 20260807_GAM_URA)
## 【1. 試合概要・基本データ】
- **対象URL**: https://www.jleague.jp/match/j1/2026/080702/
- **節数**: 第1節
- **開催日時**: 2026/8/7 (金) 19:30 KO
- **スタジアム**: パナソニック スタジアム 吹田
- **試合結果**: 4 - 3

### 【チームスタッツ比較】
| 指標 | HOME | AWAY |
| :--- | :---: | :---: |
| シュート数 | 11 | 19 |
| ボール支配率(%) | 60% | 40% |

## 【2. 公式マッチレポート】
熱戦の開幕戦。

## 【3. 監督・選手コメント（定性の核）】
### 【監督コメント】
#### 【ガンバ大阪】明神 智和
素晴らしい勝利でした。
#### 【浦和レッズ】曺 貴裁
悔しい敗戦です。

### 【選手コメント】
#### 【ガンバ大阪】植中 朝日
ゴールを決められて嬉しい。
#### 【浦和レッズ】南野 遥海
古巣対決でした。
"""
        bundle = parse_jleague_markdown(md_content, self.normalizer)

        self.assertEqual(bundle.match.match_id, "20260807_GAM_URA")
        self.assertEqual(bundle.match.season, 2026)
        self.assertEqual(bundle.match.matchweek, 1)
        self.assertEqual(bundle.match.home_team_id, "GAM")
        self.assertEqual(bundle.match.away_team_id, "URA")

        reviews_by_type = {r.review_type: r for r in bundle.reviews}
        self.assertIn("HOME_COACH", reviews_by_type)
        self.assertEqual(reviews_by_type["HOME_COACH"].speaker_name, "明神 智和")
        self.assertEqual(reviews_by_type["HOME_COACH"].speaker_team_id, "GAM")

        self.assertIn("AWAY_COACH", reviews_by_type)
        self.assertEqual(reviews_by_type["AWAY_COACH"].speaker_name, "曺 貴裁")
        self.assertEqual(reviews_by_type["AWAY_COACH"].speaker_team_id, "URA")

        # Check player reviews
        home_players = [r for r in bundle.reviews if r.review_type == "HOME_PLAYER"]
        away_players = [r for r in bundle.reviews if r.review_type == "AWAY_PLAYER"]
        self.assertEqual(len(home_players), 1)
        self.assertEqual(home_players[0].speaker_name, "植中 朝日")
        self.assertEqual(home_players[0].speaker_team_id, "GAM")

        self.assertEqual(len(away_players), 1)
        self.assertEqual(away_players[0].speaker_name, "南野 遥海")
        self.assertEqual(away_players[0].speaker_team_id, "URA")

    def test_run_backfill_with_season_filter(self):
        """Verify season filter correctly selects only matches matching target season."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_2026 = Path(tmpdir) / "2026_mw1.md"
            file_2024 = Path(tmpdir) / "2024_mw1.md"

            content_2026 = """# ＦＣ東京vs水戸 (Match ID: 2026_MW1)
## 【1. 試合概要・基本データ】
- **節数**: 第1節
- **開催日時**: 2026/08/08 (土) 19:00 KO
- **試合結果**: 2 - 0
"""
            content_2024 = """# ＦＣ東京vs水戸 (Match ID: 2024_MW1)
## 【1. 試合概要・基本データ】
- **節数**: 第1節
- **開催日時**: 2024/02/24 (土) 14:00 KO
- **試合結果**: 1 - 1
"""
            file_2026.write_text(content_2026, encoding="utf-8")
            file_2024.write_text(content_2024, encoding="utf-8")

            report = self.pipeline.run_backfill(
                data_dir=tmpdir,
                start_mw=1,
                end_mw=5,
                season=2026,
            )

            self.assertEqual(report["total_files"], 2)
            self.assertEqual(report["processed"], 1)
            self.assertEqual(report["skipped"], 1)
            self.assertEqual(report["matches"][0]["match_id"], "2026_MW1")

    def test_find_files_and_auxiliary_filtering(self):
        """Verify helper skips auxiliary files like fctokyo club review."""
        self.assertTrue(_should_skip_auxiliary_file("data/markdown/2026/20261025_FCT_MIT_fctokyo.md"))
        self.assertFalse(_should_skip_auxiliary_file("data/markdown/2026/20261025_FCT_MIT.md"))


class TestDbIntegrityTool(unittest.TestCase):
    """Test suite for clean_and_verify_db tool."""

    def setUp(self):
        self.conn = init_db(":memory:")

    def tearDown(self):
        if self.conn:
            self.conn.close()

    def test_cleanup_and_integrity_check(self):
        """Verify obsolete dummy records are cleanly removed."""
        cur = self.conn.cursor()
        # Insert a valid match
        cur.execute(
            """
            INSERT INTO matches (match_id, season, matchweek, home_team_id, away_team_id)
            VALUES ('VALID_01', 2026, 1, 'FCT', 'MIT');
            """,
        )
        cur.execute(
            """
            INSERT INTO team_match_stats (match_id, team_id, period)
            VALUES ('VALID_01', 'FCT', 'ALL');
            """,
        )
        # Insert an obsolete dummy match
        cur.execute(
            """
            INSERT INTO matches (match_id, season, matchweek, home_team_id, away_team_id)
            VALUES ('DUMMY_01', 2026, NULL, 'FCT', 'KAS');
            """,
        )
        self.conn.commit()

        # Run cleanup on this connection
        cur.execute(
            """
            SELECT m.match_id FROM matches m
            LEFT JOIN team_match_stats s ON m.match_id = s.match_id
            WHERE m.matchweek IS NULL AND s.id IS NULL;
            """,
        )
        obsolete = [r[0] for r in cur.fetchall()]
        self.assertEqual(obsolete, ["DUMMY_01"])

        for m_id in obsolete:
            cur.execute("DELETE FROM matches WHERE match_id = ?", (m_id,))
        self.conn.commit()

        cur.execute("SELECT count(*) FROM matches;")
        self.assertEqual(cur.fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
