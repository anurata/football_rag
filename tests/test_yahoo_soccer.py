"""Yahoo!サッカースクレイパーの単体テスト (tests/test_yahoo_soccer.py)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup
from scrapers.yahoo_soccer import YahooSoccerScraper

SAMPLE_STATS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Jリーグ - J1 第12節 名古屋 vs. 横浜FM - スタッツ</title></head>
<body>
  <div class="sc-scoreBoard">
    <div class="sc-scoreBoard__header">J1 第12節</div>
    <div class="sc-scoreBoard__infoItem">10/25(土) 14:00 豊田スタジアム</div>
    <div class="sc-scoreBoard__team--home"><span class="sc-scoreBoard__name">名古屋</span></div>
    <div class="sc-scoreBoard__team--away"><span class="sc-scoreBoard__name">横浜FM</span></div>
    <div class="sc-scoreBoard__scoreTotal">1 - 1</div>
  </div>

  <div class="sc-modCommon01">
    <table class="sc-tableVersus">
      <tr><th>名古屋</th><th></th><th>横浜FM</th></tr>
      <tr><td>51%</td><td>保持率</td><td>49%</td></tr>
      <tr><td>20</td><td>シュート</td><td>11</td></tr>
      <tr><td>108.586km</td><td>走行距離</td><td>112.196km</td></tr>
      <tr><td>121</td><td>スプリント</td><td>122</td></tr>
    </table>
  </div>

  <div class="sc-tablePlayerStatsWrap">
    <table class="sc-tablePlayerStats">
      <tr>
        <th rowspan="2">Pos.</th><th rowspan="2">選手名</th><th rowspan="2">チーム名</th>
        <th colspan="4">攻撃</th><th colspan="5">守備</th>
        <th colspan="3">走行距離</th><th colspan="4">スプリント</th>
        <th colspan="5">パス</th><th colspan="4">プレー数</th>
        <th colspan="2">セットプレー</th><th colspan="4">ファウル</th>
      </tr>
      <tr>
        <th>シュート</th><th>枠内</th><th>得点</th><th>ドリブル</th>
        <th>タックル</th><th>こぼれ球</th><th>ブロック</th><th>クリア</th><th>被枠内</th>
        <th>1試合</th><th>前半</th><th>後半</th>
        <th>1試合</th><th>前半</th><th>後半</th><th>最高速</th>
        <th>パス</th><th>ATサード</th><th>スルー</th><th>クロス</th><th>アシスト</th>
        <th>全</th><th>AT</th><th>ミドル</th><th>DF</th>
        <th>FK</th><th>CK</th>
        <th>警告</th><th>退場</th><th>ファウル</th><th>被ファウル</th>
      </tr>
      <tr>
        <td>FW</td><td>山岸 祐也</td><td>名古屋</td>
        <td>6</td><td>1</td><td>1</td><td>0(0%)</td>
        <td>0(0%)</td><td>3</td><td>1</td><td>0</td><td>0(0%)</td>
        <td>9.392km</td><td>4.735km</td><td>4.657km</td>
        <td>10</td><td>6</td><td>4</td><td>30.5km/h</td>
        <td>18(72.2%)</td><td>4(75%)</td><td>3(33.3%)</td><td>0(0%)</td><td>0</td>
        <td>35</td><td>15</td><td>19</td><td>1</td>
        <td>0</td><td>0</td>
        <td>0</td><td>0</td><td>0</td><td>3</td>
      </tr>
    </table>
  </div>
</body>
</html>
"""

SAMPLE_TEXT_HTML = """
<!DOCTYPE html>
<html>
<head><title>Jリーグ - J1 第12節 名古屋 vs. 横浜FM - テキスト速報</title></head>
<body>
  <div class="sc-scoreBoard">
    <div class="sc-scoreBoard__header">J1 第12節</div>
    <div class="sc-scoreBoard__infoItem">10/25(土) 14:00 豊田スタジアム</div>
    <div class="sc-scoreBoard__team--home"><span class="sc-scoreBoard__name">名古屋</span></div>
    <div class="sc-scoreBoard__team--away"><span class="sc-scoreBoard__name">横浜FM</span></div>
    <div class="sc-scoreBoard__scoreTotal">1 - 1</div>
  </div>

  <div class="sc-textLive">
    <div class="sc-textLive__item">
      <div class="sc-textLive__status">前半0分</div>
      <div class="sc-textLive__name">横浜FM</div>
      <div class="sc-textLive__text">宮市はこの試合でJ1通算100試合出場を達成</div>
    </div>
    <div class="sc-textLive__item">
      <div class="sc-textLive__status">前半14分</div>
      <div class="sc-textLive__name">横浜FM</div>
      <div class="sc-textLive__text">GOOOOOAL!! Jクルークスが左足でゴール右下に決める</div>
    </div>
    <div class="sc-textLive__item">
      <div class="sc-textLive__status">前半20分</div>
      <div class="sc-textLive__text">ここまでのシュート: 名古屋:0本、横浜FM:6本 / ゴール期待値: 名古屋:0.00、横浜FM:0.58</div>
    </div>

    <div class="sc-textLive__item">
      <div class="sc-textLive__status">後半30分</div>
      <div class="sc-textLive__name">名古屋</div>
      <div class="sc-textLive__text">選手交代: OUT 山岸 -> IN パトリック</div>
    </div>
    <div class="sc-textLive__item">
      <div class="sc-textLive__status">後半40分</div>
      <div class="sc-textLive__name">横浜FM</div>
      <div class="sc-textLive__text">警告: 危険なタックルによりイエローカード提示</div>
    </div>
  </div>
</body>
</html>
"""


class TestYahooSoccerScraper(unittest.TestCase):
    """YahooSoccerScraperのテストケース."""

    def setUp(self) -> None:
        """テストの事前準備."""
        self.scraper = YahooSoccerScraper()

    def test_parse_scoreboard(self) -> None:
        """スコアボードの抽出テスト."""
        soup = BeautifulSoup(SAMPLE_STATS_HTML, "html.parser")
        info = self.scraper._parse_scoreboard(soup)

        self.assertEqual(info["section"], "J1 第12節")
        self.assertIn("10/25(土)", info["datetime_venue"])
        self.assertEqual(info["home_team"], "名古屋")
        self.assertEqual(info["away_team"], "横浜FM")
        self.assertEqual(info["score"], "1 - 1")

    def test_parse_team_stats(self) -> None:
        """チームスタッツ比較表の抽出テスト."""
        soup = BeautifulSoup(SAMPLE_STATS_HTML, "html.parser")
        team_stats = self.scraper._parse_team_stats(soup)

        self.assertEqual(team_stats["home_team"], "名古屋")
        self.assertEqual(team_stats["away_team"], "横浜FM")

        metrics = team_stats["metrics"]
        self.assertIn("保持率", metrics)
        self.assertEqual(metrics["保持率"]["名古屋"], "51%")
        self.assertEqual(metrics["保持率"]["横浜FM"], "49%")

        self.assertIn("シュート", metrics)
        self.assertEqual(metrics["シュート"]["名古屋"], "20")
        self.assertEqual(metrics["シュート"]["横浜FM"], "11")

        self.assertIn("走行距離", metrics)
        self.assertEqual(metrics["走行距離"]["名古屋"], "108.586km")

    def test_parse_player_stats(self) -> None:
        """個人スタッツ表の抽出テスト."""
        soup = BeautifulSoup(SAMPLE_STATS_HTML, "html.parser")
        players = self.scraper._parse_player_stats(soup)

        self.assertEqual(len(players), 1)
        p = players[0]
        self.assertEqual(p["position"], "FW")
        self.assertEqual(p["player_name"], "山岸 祐也")
        self.assertEqual(p["team_name"], "名古屋")
        self.assertEqual(p["attack"]["shoot"], "6")
        self.assertEqual(p["attack"]["goals"], "1")
        self.assertEqual(p["defense"]["loose_ball_recovery"], "3")
        self.assertEqual(p["distance"]["total"], "9.392km")
        self.assertEqual(p["sprint"]["total"], "10")
        self.assertEqual(p["sprint"]["max_speed"], "30.5km/h")
        self.assertEqual(p["pass"]["pass_success"], "18(72.2%)")
        self.assertEqual(p["plays_by_area"]["total"], "35")
        self.assertEqual(p["discipline"]["suffer_foul"], "3")

    def test_parse_scorers(self) -> None:
        """得点者リストの抽出テスト."""
        scorers_html = """
        <ul class="sc-goalPlayer__list--home">
          <li class="sc-goalPlayer__listItem">
            <a class="sc-goalPlayer__name">山岸 祐也</a>
            <span class="sc-goalPlayer__time">後29'</span>
          </li>
        </ul>
        """
        soup = BeautifulSoup(scorers_html, "html.parser")
        scorers = self.scraper._parse_scorers(soup, ".sc-goalPlayer__list--home")
        self.assertEqual(len(scorers), 1)
        self.assertEqual(scorers[0]["player"], "山岸 祐也")
        self.assertEqual(scorers[0]["time"], "後29'")


    def test_parse_text_timeline(self) -> None:
        """テキスト速報タイムラインの抽出テスト."""
        soup = BeautifulSoup(SAMPLE_TEXT_HTML, "html.parser")
        timeline = self.scraper._parse_text_timeline(soup)

        self.assertEqual(len(timeline), 5)

        # 0: 通常コメント
        self.assertEqual(timeline[0]["time"], "前半0分")
        self.assertEqual(timeline[0]["team"], "横浜FM")
        self.assertFalse(timeline[0]["is_goal"])
        self.assertFalse(timeline[0]["is_card"])
        self.assertFalse(timeline[0]["is_substitution"])

        # 1: ゴール
        self.assertEqual(timeline[1]["time"], "前半14分")
        self.assertTrue(timeline[1]["is_goal"])

        # 2: チームなし（全体の状況集計）
        self.assertEqual(timeline[2]["time"], "前半20分")
        self.assertIsNone(timeline[2]["team"])
        self.assertFalse(timeline[2]["is_goal"])


        # 3: 選手交代
        self.assertEqual(timeline[3]["time"], "後半30分")
        self.assertTrue(timeline[3]["is_substitution"])

        # 4: カード提示
        self.assertEqual(timeline[4]["time"], "後半40分")
        self.assertTrue(timeline[4]["is_card"])

    @patch("requests.get")
    def test_save_raw_data(self, mock_get: MagicMock) -> None:
        """save_raw_dataのファイル出力テスト."""
        # 1回目はstats、2回目はtextを返すようにモック
        resp_stats = MagicMock()
        resp_stats.text = SAMPLE_STATS_HTML
        resp_stats.status_code = 200

        resp_text = MagicMock()
        resp_text.text = SAMPLE_TEXT_HTML
        resp_text.status_code = 200

        mock_get.side_effect = [resp_stats, resp_text]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.scraper.save_raw_data("2026102502", output_dir=tmpdir)

            stats_path = result["stats_path"]
            text_path = result["text_path"]

            self.assertTrue(os.path.exists(stats_path))
            self.assertTrue(os.path.exists(text_path))

            with open(stats_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertEqual(data["game_id"], "2026102502")
                self.assertEqual(data["match_info"]["home_team"], "名古屋")
                self.assertEqual(len(data["player_stats"]), 1)

            with open(text_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertEqual(data["game_id"], "2026102502")
                self.assertEqual(len(data["timeline"]), 5)


if __name__ == "__main__":
    unittest.main()
