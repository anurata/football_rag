"""
Unit tests for 2026 Season J1 Crawler and Canonical Match ID Resolution.
"""

import unittest
from bs4 import BeautifulSoup

from pipeline.normalizer import EntityNormalizer
from scrapers.jleague_official import resolve_canonical_match_id


class TestCrawler2026(unittest.TestCase):
    """Test canonical match resolution and crawler logic."""

    def setUp(self):
        self.normalizer = EntityNormalizer()

    def test_resolve_canonical_match_id_from_h1(self):
        """H1に 'チームA vs チームB' がある場合の正常解決テスト。"""
        html = """
        <html>
            <head><title>【公式】ＦＣ東京 vs ＦＣ町田ゼルビアの試合結果 | Ｊリーグ</title></head>
            <body>
                <h1>ＦＣ東京vsＦＣ町田ゼルビア</h1>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        url = "https://www.jleague.jp/match/j1/2026/080802/"

        match_id, title = resolve_canonical_match_id(
            soup=soup,
            url=url,
            normalizer=self.normalizer,
        )
        self.assertEqual(match_id, "20260808_FCT_ZEL")
        self.assertIn("ＦＣ東京", title)
        self.assertIn("町田", title)

    def test_resolve_canonical_match_id_from_title(self):
        """H1にvsがなくTitleから抽出する場合のテスト。"""
        html = """
        <html>
            <head><title>【公式】サンフレッチェ広島 vs ジェフユナイテッド千葉の試合結果・データ（明治安田Ｊ１リーグ：2026年8月8日） | Ｊリーグ</title></head>
            <body>
                <h1>検索</h1>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        url = "https://www.jleague.jp/match/j1/2026/080806/"

        match_id, title = resolve_canonical_match_id(
            soup=soup,
            url=url,
            normalizer=self.normalizer,
        )
        self.assertEqual(match_id, "20260808_HIR_JEF")

    def test_reject_j2_match(self):
        """J2リーグの試合ページはNoneを返すテスト。"""
        html = """
        <html>
            <head><title>【公式】札幌 vs 徳島の試合結果・データ（明治安田Ｊ２リーグ：2026年8月8日） | Ｊリーグ</title></head>
            <body>
                <h1>札幌vs徳島</h1>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        url = "https://www.jleague.jp/match/j1/2026/080807/"

        match_id, title = resolve_canonical_match_id(
            soup=soup,
            url=url,
            normalizer=self.normalizer,
        )
        self.assertIsNone(match_id)
        self.assertIsNone(title)

    def test_reject_404_or_search(self):
        """404や検索ページはNoneを返すテスト。"""
        html = """
        <html>
            <head><title>404 Not Found | Ｊリーグ</title></head>
            <body>
                <h1>ページが見つかりません</h1>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        url = "https://www.jleague.jp/match/j1/2026/080899/"

        match_id, title = resolve_canonical_match_id(
            soup=soup,
            url=url,
            normalizer=self.normalizer,
        )
        self.assertIsNone(match_id)


if __name__ == "__main__":
    unittest.main()
