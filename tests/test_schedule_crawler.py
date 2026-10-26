"""
Unit tests for ScheduleCrawler (tests/test_schedule_crawler.py).
"""

import unittest
from scrapers.schedule_crawler import ScheduleCrawler
from pipeline.normalizer import EntityNormalizer


SAMPLE_TABLE_HTML = """
<table>
  <tr>
    <th>年度</th><th>大会</th><th>節</th><th>試合日</th><th>K/O</th><th>ホーム</th><th>スコア</th><th>アウェイ</th><th>スタジアム</th><th>入場者数</th>
  </tr>
  <tr>
    <td>2024</td><td>Ｊ１</td><td>第１節第１日</td><td>24/02/23(金・祝)</td><td>14:06</td>
    <td>広島</td><td><a href="/SFMS02/?match_card_id=30430">2-0</a></td><td>浦和</td><td>Ｅピース</td><td>27,545</td>
  </tr>
  <tr>
    <td>2024</td><td>Ｊ１</td><td>第１節第１日</td><td>24/02/23(金・祝)</td><td>18:03</td>
    <td>名古屋</td><td><a href="/SFMS02/?match_card_id=30431">0-3</a></td><td>鹿島</td><td>豊田ス</td><td>36,933</td>
  </tr>
  <tr>
    <td>2024</td><td>Ｊ１</td><td>第２節第１日</td><td>24/03/01(金)</td><td>19:03</td>
    <td>川崎Ｆ</td><td><a href="/SFMS02/?match_card_id=30440">4-5</a></td><td>磐田</td><td>Ｕ等々力</td><td>20,316</td>
  </tr>
  <tr>
    <td>2024</td><td>Ｊ１</td><td>第13節第１日</td><td>24/05/11(土)</td><td>14:03</td>
    <td>新潟</td><td><a href="/SFMS02/?match_card_id=30550">2-4</a></td><td>浦和</td><td>デンカＳ</td><td>24,539</td>
  </tr>
</table>
"""


class TestScheduleCrawler(unittest.TestCase):
    def setUp(self):
        self.crawler = ScheduleCrawler()

    def test_parse_matchweek_number(self):
        self.assertEqual(self.crawler.parse_matchweek_number("第１節第１日"), 1)
        self.assertEqual(self.crawler.parse_matchweek_number("第12節第２日"), 12)
        self.assertIsNone(self.crawler.parse_matchweek_number("準決勝"))

    def test_parse_date_and_time(self):
        res = self.crawler.parse_date_and_time("24/02/23(金・祝)", "14:06", year=2024)
        self.assertEqual(res["date"], "2024-02-23")
        self.assertEqual(res["mmdd"], "0223")
        self.assertEqual(res["time"], "14:06")

    def test_parse_schedule_rows(self):
        rows = self.crawler.parse_schedule_rows(SAMPLE_TABLE_HTML, year=2024)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["home_team_id"], "HIR")
        self.assertEqual(rows[0]["away_team_id"], "URA")
        self.assertEqual(rows[0]["card_id"], "30430")

    def test_build_schedule_mw_filtering(self):
        # Filter MW 1 to 2 (excludes MW 13)
        matches = self.crawler.build_schedule(
            html_content=SAMPLE_TABLE_HTML,
            year=2024,
            start_mw=1,
            end_mw=2,
        )
        self.assertEqual(len(matches), 3)

        # Check daily sequence and match_id formatting
        m1 = matches[0]
        self.assertEqual(m1["match_id"], "20240223_HIR_URA")
        self.assertEqual(m1["daily_match_index"], 1)
        self.assertEqual(m1["official_url"], "https://www.jleague.jp/match/j1/2024/022301/")

        m2 = matches[1]
        self.assertEqual(m2["match_id"], "20240223_NAG_KAS")
        self.assertEqual(m2["daily_match_index"], 2)
        self.assertEqual(m2["official_url"], "https://www.jleague.jp/match/j1/2024/022302/")

        m3 = matches[2]
        self.assertEqual(m3["matchweek"], 2)
        self.assertEqual(m3["daily_match_index"], 1)
        self.assertEqual(m3["official_url"], "https://www.jleague.jp/match/j1/2024/030101/")


if __name__ == "__main__":
    unittest.main()
