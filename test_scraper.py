import os
import unittest
from bs4 import BeautifulSoup
from scraper import (
    extract_match_title,
    extract_basic_info,
    extract_team_stats,
    extract_match_report,
    extract_comments,
    format_comments_markdown,
    format_stats_markdown,
    build_markdown_content,
)


class TestScraper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        match_html_path = os.path.join(base_dir, "page_match.html")
        review_html_path = os.path.join(base_dir, "page_review.html")

        with open(match_html_path, "r", encoding="utf-8") as f:
            cls.match_soup = BeautifulSoup(f.read(), "html.parser")

        with open(review_html_path, "r", encoding="utf-8") as f:
            cls.review_soup = BeautifulSoup(f.read(), "html.parser")

    def test_extract_match_title(self):
        title = extract_match_title(self.match_soup, "test_id")
        self.assertIn("ＦＣ東京", title)
        self.assertIn("水戸ホーリーホック", title)
        self.assertNotEqual(title, "検索")

    def test_extract_basic_info(self):
        info = extract_basic_info(self.match_soup)
        self.assertIn("2026/10/25", info["date"])
        self.assertEqual(info["stadium"], "味の素スタジアム")
        self.assertEqual(info["attendance"], "23,602人")
        self.assertIn("24℃", info["climate"])
        self.assertEqual(info["score"], "6 - 0")
        self.assertTrue(len(info["scorers"]) > 0)
        self.assertIn("仲川 輝人 32'", info["scorers"])

    def test_extract_team_stats(self):
        stats = extract_team_stats(self.match_soup)
        self.assertTrue(len(stats) > 0)

        # シュート数
        shoot_stat = next((s for s in stats if "シュート数" == s["label"]), None)
        self.assertIsNotNone(shoot_stat)
        self.assertEqual(shoot_stat["home"], "23")
        self.assertEqual(shoot_stat["away"], "12")

        # ボール支配率
        possession_stat = next((s for s in stats if "ボール支配率" in s["label"]), None)
        self.assertIsNotNone(possession_stat)
        self.assertIn("55", possession_stat["home"])
        self.assertIn("45", possession_stat["away"])

        # 警告・退場
        card_stat = next((s for s in stats if "警告・退場" in s["label"]), None)
        self.assertIsNotNone(card_stat)
        self.assertEqual(card_stat["home"], "警告:1 / 退場:0")
        self.assertEqual(card_stat["away"], "警告:0 / 退場:0")

    def test_extract_match_report(self):
        report = extract_match_report(self.review_soup)
        self.assertNotEqual(report, "マッチレポートが見つかりませんでした。")
        self.assertIn("FC東京はホームに水戸を迎えた", report)
        self.assertIn("河合 萌花", report)
        # 不要な「続きを読む」ボタンテキストが含まれていないこと
        self.assertNotIn("続きを読む", report)

    def test_extract_coach_comments(self):
        coach_comments = extract_comments(self.review_soup, "監督コメント")
        self.assertEqual(len(coach_comments), 2)

        names = [c["name"] for c in coach_comments]
        self.assertIn("松橋 力蔵", names)
        self.assertIn("樹森 大介", names)

        fc_coach = next(c for c in coach_comments if c["name"] == "松橋 力蔵")
        self.assertEqual(fc_coach["club"], "ＦＣ東京")
        self.assertIn("大量得点", fc_coach["content"])

        mito_coach = next(c for c in coach_comments if c["name"] == "樹森 大介")
        self.assertEqual(mito_coach["club"], "水戸ホーリーホック")
        self.assertIn("残念な結果になりました", mito_coach["content"])

    def test_extract_player_comments(self):
        player_comments = extract_comments(self.review_soup, "選手コメント")
        self.assertEqual(len(player_comments), 4)

        names = [c["name"] for c in player_comments]
        self.assertIn("ダニ ゴメス", names)
        self.assertIn("安斎 颯馬", names)
        self.assertIn("キム スンギュ", names)
        self.assertIn("木本 恭生", names)

        dani = next(c for c in player_comments if c["name"] == "ダニ ゴメス")
        self.assertEqual(dani["club"], "ＦＣ東京")
        self.assertIn("ニアのポストに走り込んで", dani["content"])

        kimoto = next(c for c in player_comments if c["name"] == "木本 恭生")
        self.assertEqual(kimoto["club"], "水戸ホーリーホック")
        self.assertIn("古巣との戦い", kimoto["content"])

    def test_build_markdown_content(self):
        basic_info = {
            "date": "2026/10/25 (日) 16:03 KO",
            "stadium": "味の素スタジアム",
            "attendance": "23,602人",
            "climate": "天候:曇り｜気温:24℃｜湿度:90%",
            "score": "6 - 0",
            "scorers": ["仲川 輝人32'"],
        }
        stats = [
            {
                "label": "シュート数",
                "home": "23",
                "away": "12",
            },
        ]
        coach_comments = [
            {
                "club": "ＦＣ東京",
                "name": "松橋 力蔵",
                "content": "良い試合だった。",
            },
        ]
        player_comments = [
            {
                "club": "水戸ホーリーホック",
                "name": "木本 恭生",
                "content": "悔しい。",
            },
        ]

        md = build_markdown_content(
            match_id="TEST_ID",
            base_url="https://example.com",
            title="FC東京 vs 水戸ホーリーホック",
            basic_info=basic_info,
            stats=stats,
            report_text="熱戦が繰り広げられた。",
            coach_comments=coach_comments,
            player_comments=player_comments,
        )

        self.assertIn("# FC東京 vs 水戸ホーリーホック (Match ID: TEST_ID)", md)
        self.assertIn("味の素スタジアム", md)
        self.assertIn("| シュート数 | 23 | 12 |", md)
        self.assertIn("熱戦が繰り広げられた。", md)
        self.assertIn("#### 【ＦＣ東京】松橋 力蔵", md)
        self.assertIn("#### 【水戸ホーリーホック】木本 恭生", md)


if __name__ == "__main__":
    unittest.main()
