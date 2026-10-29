import os
import unittest
from jleague_player_scraper import (
    evaluate_strong_points,
    extract_player_id_from_url,
    parse_club_players_html,
    parse_player_detail_html,
)


class TestJLeaguePlayerScraper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        fixture_dir = os.path.join(base_dir, "fixtures")

        club_path = os.path.join(fixture_dir, "sample_club_players.html")
        with open(club_path, "r", encoding="utf-8") as f:
            cls.club_html = f.read()

        player_path = os.path.join(fixture_dir, "sample_player_page.html")
        with open(player_path, "r", encoding="utf-8") as f:
            cls.player_html = f.read()

    def test_extract_player_id_from_url(self):
        url1 = "https://www.jleague.jp/player/1632774/"
        url2 = "/player/1400645/"
        url3 = "https://www.jleague.jp/other/path"

        self.assertEqual(extract_player_id_from_url(url1), "1632774")
        self.assertEqual(extract_player_id_from_url(url2), "1400645")
        self.assertEqual(extract_player_id_from_url(url3), "")

    def test_parse_club_players_html(self):
        players = parse_club_players_html(self.club_html)
        self.assertGreater(len(players), 30)

        # 室屋選手の確認
        muroya = next((p for p in players if p["player_id"] == "1400645"), None)
        self.assertIsNotNone(muroya)
        self.assertEqual(muroya["name"], "室屋 成")
        self.assertEqual(muroya["position"], "DF")
        self.assertEqual(muroya["number"], "2")
        self.assertEqual(muroya["birthplace"], "大阪府")
        self.assertEqual(muroya["birthdate"], "1994/4/5")
        self.assertEqual(muroya["height_cm"], "178")
        self.assertEqual(muroya["weight_kg"], "70")
        self.assertTrue(muroya["thumbnail_url"].endswith(".webp"))
        self.assertIn("https://www.jleague.jp/player/1400645/", muroya["detail_url"])

    def test_parse_player_detail_html(self):
        foot_master = {"長倉 幹樹": "右足"}
        detail = parse_player_detail_html(
            html=self.player_html,
            player_id="1632774",
            foot_master=foot_master,
        )

        self.assertEqual(detail["player_id"], "1632774")
        self.assertEqual(detail["name"], "長倉 幹樹")
        self.assertEqual(detail["name_en"], "NAGAKURA Motoki")
        self.assertEqual(detail["club_name"], "ＦＣ東京")
        self.assertEqual(detail["position"], "FW")
        self.assertEqual(detail["number"], "26")
        self.assertEqual(detail["dominant_foot"], "右足")
        self.assertEqual(detail["birthplace"], "埼玉県")
        self.assertEqual(detail["birthdate"], "1999/10/7")
        self.assertEqual(detail["height_cm"], "177")
        self.assertEqual(detail["weight_kg"], "71")
        self.assertEqual(detail["jleague_debut"], "2022/8/16")
        self.assertEqual(detail["jleague_first_goal"], "2022/8/20")

        # 高解像度画像URL
        self.assertTrue(detail["photo_url"].startswith("https://www.jleague.jp/"))
        self.assertTrue(detail["photo_url"].endswith("1632774_l.webp"))

        # シーズンスタッツ
        stats = detail["season_stats"]
        self.assertIn("総スプリント回数", stats)
        self.assertEqual(stats["総スプリント回数"], 222)
        self.assertEqual(stats["枠内シュート総数"], 13)
        self.assertEqual(stats["チャンスクリエイト総数"], 22)
        self.assertEqual(stats["デュエル勝利総数"], 20)
        self.assertEqual(stats["総走行距離"], 121.8)

        # ストロングポイント判定
        strong_points = detail["strong_points"]
        self.assertGreater(len(strong_points), 0)
        sp_text = " ".join(strong_points)
        self.assertIn("スプリント力", sp_text)
        self.assertIn("ラストパス", sp_text)
        self.assertIn("枠内シュート", sp_text)

        # キャリア履歴
        career = detail["career_history"]
        self.assertGreater(len(career), 0)
        clubs = [c["club"] for c in career]
        self.assertTrue(any("新潟" in c for c in clubs))
        self.assertTrue(any("浦和" in c for c in clubs))

    def test_evaluate_strong_points_custom(self):
        # 空中戦特化型CFのテスト
        cf_stats = {
            "空中戦勝利数": 25,
            "デュエル勝利総数": 18,
            "総スプリント回数": 50,
        }
        sp = evaluate_strong_points(cf_stats, "FW", height_cm="190")
        combined = " ".join(sp)
        self.assertIn("空中戦", combined)
        self.assertIn("デュエル", combined)

        # スタッツが少ない場合のデフォルトフォールバックテスト
        empty_sp = evaluate_strong_points({}, "GK")
        self.assertEqual(len(empty_sp), 1)
        self.assertIn("シュートストップ", empty_sp[0])


if __name__ == "__main__":
    unittest.main()
