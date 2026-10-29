"""Yahoo!サッカースクレイパーの単体テスト (tests/test_yahoo_soccer.py)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup
from scrapers.yahoo_soccer import (
    YahooSoccerScraper,
    infer_panel_tactical_roles,
    parse_yahoo_minute_label,
)

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

    def test_parse_yahoo_minute_label(self) -> None:
        """時間ラベルの通算分変換テスト."""
        self.assertEqual(parse_yahoo_minute_label("前半0分"), 0)
        self.assertEqual(parse_yahoo_minute_label("前半39分"), 39)
        self.assertEqual(parse_yahoo_minute_label("後半0分"), 45)
        self.assertEqual(parse_yahoo_minute_label("後半18分"), 63)

    def test_infer_panel_tactical_roles_multi_formations(self) -> None:
        """4-2-3-1 と 3-4-2-1 それぞれの座標から戦術ロールとレーンが正確に推論されるか検証."""
        items_4231 = [
            {"number": "1", "x": -148, "y": 0},
            {"number": "2", "x": -101, "y": 77},
            {"number": "4", "x": -101, "y": 33},
            {"number": "5", "x": -101, "y": -33},
            {"number": "6", "x": -101, "y": -77},
            {"number": "8", "x": -71, "y": 33},
            {"number": "16", "x": -71, "y": -33},
            {"number": "14", "x": -35, "y": 44},
            {"number": "10", "x": -35, "y": 0},
            {"number": "7", "x": -35, "y": -44},
            {"number": "9", "x": -9, "y": 0},
        ]
        res_4231 = {p["number"]: p for p in infer_panel_tactical_roles(items_4231, "4-2-3-1")}
        self.assertEqual(res_4231["2"]["inferred_role"], "RSB")
        self.assertEqual(res_4231["2"]["inferred_lane"], "RIGHT")
        self.assertEqual(res_4231["4"]["inferred_role"], "RCB")
        self.assertEqual(res_4231["5"]["inferred_role"], "LCB")
        self.assertEqual(res_4231["6"]["inferred_role"], "LSB")
        self.assertEqual(res_4231["14"]["inferred_role"], "RSH")
        self.assertEqual(res_4231["10"]["inferred_role"], "OMF")
        self.assertEqual(res_4231["7"]["inferred_role"], "LSH")
        self.assertEqual(res_4231["9"]["inferred_role"], "CF")

        items_3421 = [
            {"number": "1", "x": -148, "y": 0},
            {"number": "3", "x": -101, "y": 44},
            {"number": "50", "x": -101, "y": 0},
            {"number": "19", "x": -101, "y": -44},
            {"number": "88", "x": -71, "y": 88},
            {"number": "16", "x": -71, "y": 33},
            {"number": "31", "x": -71, "y": -33},
            {"number": "33", "x": -71, "y": -88},
            {"number": "15", "x": -35, "y": 33},
            {"number": "7", "x": -35, "y": -33},
            {"number": "99", "x": -9, "y": 0},
        ]
        res_3421 = {p["number"]: p for p in infer_panel_tactical_roles(items_3421, "3-4-2-1")}
        self.assertEqual(res_3421["3"]["inferred_role"], "RCB")
        self.assertEqual(res_3421["50"]["inferred_role"], "CCB")
        self.assertEqual(res_3421["19"]["inferred_role"], "LCB")
        self.assertEqual(res_3421["88"]["inferred_role"], "RWB")
        self.assertEqual(res_3421["33"]["inferred_role"], "LWB")
        self.assertEqual(res_3421["15"]["inferred_role"], "RST")
        self.assertEqual(res_3421["7"]["inferred_role"], "LST")

    @patch("requests.get")
    def test_fetch_and_save_summary_snapshots(self, mock_get: MagicMock) -> None:
        """/summaryの時間帯別フォーメーション推移とrowspanメンバー結合のテスト."""
        sample_summary_html = """
        <html><body>
          <div class="sc-scoreBoard">
            <div class="sc-scoreBoard__header">J1 第12節</div>
            <div class="sc-scoreBoard__team--home"><span class="sc-scoreBoard__name">FC東京</span></div>
            <div class="sc-scoreBoard__team--away"><span class="sc-scoreBoard__name">水戸</span></div>
            <div class="sc-scoreBoard__scoreTotal">6 - 0</div>
          </div>
          <div><header class="sc-head01"><h2>戦評</h2></header><p>FC東京が快勝。</p></div>
          <div class="sc-formation">
            <div class="sc-formation__team--home">
              <p class="js-changeFormation">4-4-2</p>
              <p class="js-changeFormation">4-4-2</p>
            </div>
            <div class="sc-formation__change">
              <p class="js-changeTime">前半0分</p>
              <p class="js-changeTime">後半18分</p>
            </div>
            <div class="sc-formation__team--away">
              <p class="js-changeFormation">4-4-2</p>
              <p class="js-changeFormation">4-4-2</p>
            </div>
            <div class="sc-formation__panelBack">
              <div class="sc-formation__panel sc-formation__panel--home">
                <div class="sc-formation__item sc-formation__item--x-101 sc-formation__item--y-77">
                  <div class="sc-formation__itemPlayer">DF <span class="sc-formation__itemNumber">6</span> <span class="sc-formation__itemName">バングーナガンデ</span></div>
                </div>
                <div class="sc-formation__item sc-formation__item--x-53 sc-formation__item--y77">
                  <div class="sc-formation__itemPlayer">MF <span class="sc-formation__itemNumber">10</span> <span class="sc-formation__itemName">佐藤恵</span></div>
                </div>
              </div>
              <div class="sc-formation__panel sc-formation__panel--away">
                <div class="sc-formation__item sc-formation__item--x-101 sc-formation__item--y77">
                  <div class="sc-formation__itemPlayer">DF <span class="sc-formation__itemNumber">25</span> <span class="sc-formation__itemName">真瀬</span></div>
                </div>
              </div>
              <div class="sc-formation__panel sc-formation__panel--home">
                <div class="sc-formation__item sc-formation__item--x-101 sc-formation__item--y-77">
                  <div class="sc-formation__itemPlayer">MF <span class="sc-formation__itemNumber">10</span> <span class="sc-formation__itemName">佐藤恵</span> <span class="sc-formation__itemName sc-formation__itemName--out">バングーナガンデ</span></div>
                </div>
              </div>
              <div class="sc-formation__panel sc-formation__panel--away">
                <div class="sc-formation__item sc-formation__item--x-101 sc-formation__item--y77">
                  <div class="sc-formation__itemPlayer">DF <span class="sc-formation__itemNumber">25</span> <span class="sc-formation__itemName">真瀬</span></div>
                </div>
              </div>
            </div>
          </div>
          <table class="sc-tableSplits">
            <tr><th>Pos.</th><th>背番号</th><th>選手名</th><th>交代</th></tr>
            <tr><td>DF</td><td>6</td><td>バングーナガンデ 佳史扶</td><td>アウト後半18分</td></tr>
            <tr><td>MF</td><td>10</td><td>佐藤 恵允</td><td></td></tr>
          </table>
          <table class="sc-tableSplits">
            <tr><th>Pos.</th><th>背番号</th><th>選手名</th><th>交代</th></tr>
            <tr><td>DF</td><td>25</td><td>真瀬 拓海</td><td></td></tr>
          </table>
          <table class="sc-tableSplits"><tr><th>Pos.</th><th>背番号</th><th>選手名</th><th>交代</th></tr></table>
          <table class="sc-tableSplits"><tr><th>Pos.</th><th>背番号</th><th>選手名</th><th>交代</th></tr></table>
          <table class="sc-tableSplits"><tr><th>監督名</th></tr><tr><td>松橋 力蔵</td></tr></table>
          <table class="sc-tableSplits"><tr><th>監督名</th></tr><tr><td>樹森 大介</td></tr></table>
        </body></html>
        """
        resp = MagicMock()
        resp.text = sample_summary_html
        resp.status_code = 200
        mock_get.return_value = resp

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = self.scraper.save_summary_data("2026102505", output_dir=tmpdir, save_game_id="20261025_FCT_MIT")
            self.assertTrue(os.path.exists(out_path))
            with open(out_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        self.assertEqual(data["lineup"]["home"]["manager"], "松橋 力蔵")
        snaps = data["formation_snapshots"]
        self.assertEqual(len(snaps), 2)
        # Snapshot 0 (0分): 佐藤恵允は RSH
        s0_p10 = [p for p in snaps[0]["home_players"] if p["number"] == "10"][0]
        self.assertEqual(s0_p10["player_name"], "佐藤 恵允")
        self.assertEqual(s0_p10["inferred_role"], "RSH")
        # Snapshot 1 (後半18分=63分): 佐藤恵允が LSB へコンバートされた推移を検出
        self.assertEqual(snaps[1]["minute_approx"], 63)
        s1_p10 = [p for p in snaps[1]["home_players"] if p["number"] == "10"][0]
        self.assertEqual(s1_p10["inferred_role"], "LSB")
        self.assertEqual(s1_p10["replaced_out_name"], "バングーナガンデ")


if __name__ == "__main__":
    unittest.main()
