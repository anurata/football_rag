import os
import unittest
from bs4 import BeautifulSoup
from football_lab_scraper import (
    extract_flab_report_text,
    extract_flab_players,
    extract_flab_stats,
    extract_flab_cbp,
    extract_flab_timeline_blocks,
    extract_flab_script_data,
    extract_flab_heatmaps,
    extract_flab_team_style,
    build_flab_markdown,
)


class TestFootballLabScraper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(base_dir, "scratch", "page_flab_1021.html")

        with open(html_path, "r", encoding="utf-8") as f:
            cls.html = f.read()
            cls.soup = BeautifulSoup(cls.html, "html.parser")

    def test_extract_report_text(self):
        report = extract_flab_report_text(self.soup)
        self.assertNotEqual(report, "戦評データなし")
        self.assertIn("FC東京", report)

    def test_extract_players(self):
        players_data = extract_flab_players(self.soup)

        # HOME (FC東京)
        self.assertEqual(players_data["home"]["name"], "ＦＣ東京")
        self.assertIn("松橋", players_data["home"]["coach"])
        home_starting = players_data["home"]["starting"]
        self.assertEqual(len(home_starting), 11)
        self.assertEqual(home_starting[0]["name"], "キム　スンギュ")
        self.assertEqual(home_starting[0]["position"], "GK")

        # カード判定
        inamura = next((p for p in home_starting if "稲村" in p["name"]), None)
        self.assertIsNotNone(inamura)
        self.assertIn("警告", inamura["card"])

        # AWAY (柏レイソル)
        self.assertEqual(players_data["away"]["name"], "柏レイソル")
        self.assertIn("リカルド", players_data["away"]["coach"])
        away_starting = players_data["away"]["starting"]
        self.assertEqual(len(away_starting), 11)

    def test_extract_stats(self):
        stats = extract_flab_stats(self.soup)
        self.assertTrue(len(stats) > 0)

        # ゴール期待値
        xg = next((s for s in stats if "ゴール期待値" in s["name"]), None)
        self.assertIsNotNone(xg)
        self.assertEqual(xg["home_val"], "1.558")
        self.assertEqual(xg["away_val"], "1.512")

        # 総移動距離
        dist = next((s for s in stats if "総移動距離" in s["name"]), None)
        self.assertIsNotNone(dist)
        self.assertIn("117,959", dist["home_val"])

        # スプリント
        sprint = next((s for s in stats if "スプリント" in s["name"]), None)
        self.assertIsNotNone(sprint)
        self.assertEqual(sprint["home_val"], "121")

    def test_extract_cbp(self):
        cbp_data = extract_flab_cbp(self.soup)

        # チーム比較
        self.assertTrue(len(cbp_data["team"]) > 0)
        attack_team = next((t for t in cbp_data["team"] if t["name"] == "攻撃"), None)
        self.assertIsNotNone(attack_team)
        self.assertEqual(attack_team["home_val"], "23.87")

        # カテゴリ別選手ランキング
        categories = cbp_data["categories"]
        for cat in ["攻撃", "パス", "クロス", "ドリブル", "シュート", "奪取", "守備", "セーブ"]:
            self.assertIn(cat, categories)
            self.assertTrue(len(categories[cat]) > 0)

        # パストップ
        pass_top = categories["パス"]
        self.assertTrue(any("高" in p["home_player"] for p in pass_top))

    def test_extract_timeline_blocks(self):
        blocks = extract_flab_timeline_blocks(self.soup)
        self.assertTrue(len(blocks) >= 6)
        periods = [b["period"] for b in blocks]
        self.assertIn("00-15", periods)
        self.assertIn("16-30", periods)
        self.assertIn("76-90", periods)

    def test_extract_script_data(self):
        data = extract_flab_script_data(self.html)

        # 攻撃フロー推移
        self.assertEqual(len(data["stream_1st"]), 51)
        self.assertEqual(len(data["stream_2nd"]), 51)
        self.assertEqual(data["stream_1st"][0]["min"], 0)

        # シュート位置
        self.assertEqual(len(data["home_shots"]), 18)
        self.assertEqual(len(data["away_shots"]), 11)
        first_shot = data["home_shots"][0]
        self.assertIn("from_x", first_shot)
        self.assertIn("to_x", first_shot)

    def test_extract_heatmaps(self):
        heatmaps = extract_flab_heatmaps(self.soup)
        self.assertEqual(len(heatmaps), 4)
        for hz in heatmaps:
            self.assertEqual(len(hz["grid"]), 6)  # 6行
            self.assertEqual(len(hz["grid"][0]), 9)  # 9列

    def test_build_flab_markdown(self):
        dummy_players = {
            "home": {
                "name": "FC東京",
                "coach": "松橋力蔵",
                "starting": [
                    {
                        "position": "GK",
                        "number": "81",
                        "name": "キム スンギュ",
                        "minutes": "90分",
                        "change": "フル出場",
                        "card": "-",
                    },
                ],
                "substitutes": [],
            },
            "away": {
                "name": "柏レイソル",
                "coach": "リカルド",
                "starting": [],
                "substitutes": [],
            },
        }

        md = build_flab_markdown(
            match_id="TEST_ID",
            url="https://example.com/report",
            title="FC東京 vs 柏レイソル",
            report_text="激戦となった。",
            players_data=dummy_players,
            stats=[
                {
                    "name": "ゴール期待値",
                    "home_val": "1.55",
                    "home_rate": "-",
                    "away_val": "1.51",
                    "away_rate": "-",
                    "home_avg": "1.7",
                    "away_avg": "1.5",
                },
            ],
            cbp_data={
                "team": [],
                "categories": {},
            },
            timeline_blocks=[],
            script_data={
                "stream_1st": [],
                "stream_2nd": [],
                "home_shots": [],
                "away_shots": [],
            },
            heatmaps=[],
            team_styles=[],
        )

        self.assertIn("# FC東京 vs 柏レイソル (Match ID: TEST_ID)", md)
        self.assertIn("激戦となった。", md)
        self.assertIn("キム スンギュ", md)
        self.assertIn("| ゴール期待値 | 1.55 |", md)

    def test_extract_player_cbp_matrix(self):
        """選手個別CBP獲得マトリクスの集約テスト."""
        cbp_data = extract_flab_cbp(self.soup)
        self.assertIn("player_matrix", cbp_data)
        matrix = cbp_data["player_matrix"]
        self.assertGreater(len(matrix), 20)

        # 高宇洋のCBPチェック
        ko = next((p for p in matrix if "高" in p["player_name"]), None)
        self.assertIsNotNone(ko)
        self.assertEqual(ko["team_side"], "HOME")
        self.assertGreater(ko["gain"], 15.0)  # 奪取20.78
        self.assertGreater(ko["pass"], 2.0)   # パス2.74

    def test_football_lab_scraper_class(self):
        """FootballLabScraperのスラッグ解決およびURL生成テスト."""
        from scrapers.football_lab import FootballLabScraper

        scraper = FootballLabScraper()
        self.assertEqual(scraper.get_club_slug("FCT"), "fctk")
        self.assertEqual(scraper.get_club_slug("FC東京"), "fctk")
        self.assertEqual(scraper.get_club_slug("浦和"), "uraw")
        self.assertEqual(scraper.get_club_slug("ZEL"), "mcd")

        url = scraper.build_match_url("FCT", "2026-10-21")
        self.assertEqual(
            url,
            "https://www.football-lab.jp/fctk/report/?year=2026&month=10&date=21",
        )


if __name__ == "__main__":
    unittest.main()

