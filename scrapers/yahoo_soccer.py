"""Yahoo!サッカー（sports.yahoo.co.jp / soccer.yahoo.co.jp）のデータスクレイパー.

Jリーグの試合スタッツ（チームスタッツ、個人スタッツ）および
テキスト速報タイムラインを取得・パースしてJSON保存する.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


class YahooSoccerScraper:
    """Yahoo!サッカーのスタッツ・テキスト速報スクレイパー."""

    BASE_URL = "https://soccer.yahoo.co.jp/jleague/category/j1/game"

    def __init__(self, headers: Optional[Dict[str, str]] = None) -> None:
        """スクレイパーを初期化する."""
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    def fetch_stats(self, game_id: str) -> Dict[str, Any]:
        """指定されたgame_idのスタッツページを取得・解析する.

        Args:
            game_id: 試合ID (例: '2026102502')

        Returns:
            スコア情報、チームスタッツ、個人スタッツを含む辞書
        """
        url = f"{self.BASE_URL}/{game_id}/stats"
        resp = requests.get(url, headers=self.headers, timeout=15)
        resp.encoding = "utf-8"
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        scoreboard = self._parse_scoreboard(soup)
        team_stats = self._parse_team_stats(soup)
        player_stats = self._parse_player_stats(soup)

        return {
            "game_id": game_id,
            "url": url,
            "match_info": scoreboard,
            "team_stats": team_stats,
            "player_stats": player_stats,
        }

    def fetch_text_live(self, game_id: str) -> Dict[str, Any]:
        """指定されたgame_idのテキスト速報ページを取得・解析する.

        Args:
            game_id: 試合ID (例: '2026102502')

        Returns:
            試合メタ情報および時系列テキスト速報リストを含む辞書
        """
        url = f"{self.BASE_URL}/{game_id}/text"
        resp = requests.get(url, headers=self.headers, timeout=15)
        resp.encoding = "utf-8"
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        scoreboard = self._parse_scoreboard(soup)
        timeline = self._parse_text_timeline(soup)

        return {
            "game_id": game_id,
            "url": url,
            "match_info": scoreboard,
            "timeline": timeline,
        }

    def save_raw_data(
        self,
        game_id: str,
        output_dir: str = "data/raw/yahoo",
    ) -> Dict[str, str]:
        """スタッツとテキスト速報を取得し、JSONファイルとして保存する.

        Args:
            game_id: 試合ID
            output_dir: 出力先ディレクトリ

        Returns:
            保存したファイルパスの辞書
        """
        os.makedirs(output_dir, exist_ok=True)

        stats_data = self.fetch_stats(game_id)
        text_data = self.fetch_text_live(game_id)

        stats_path = os.path.join(output_dir, f"{game_id}_stats.json")
        text_path = os.path.join(output_dir, f"{game_id}_text.json")

        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats_data, f, ensure_ascii=False, indent=2)

        with open(text_path, "w", encoding="utf-8") as f:
            json.dump(text_data, f, ensure_ascii=False, indent=2)

        return {
            "stats_path": stats_path,
            "text_path": text_path,
        }

    # -------------------------------------------------------------------------
    # 内部パースメソッド群（ネストを浅く保つための分割設計）
    # -------------------------------------------------------------------------

    def _parse_scoreboard(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """ヘッダーやスコアボードから試合概要を抽出する."""
        header_title = self._get_text_by_selector(
            soup,
            ".sc-gameHeader__title, .sc-scoreBoard__header, .sc-scoreBoard__title",
        )
        meta_info = self._get_text_by_selector(
            soup,
            ".sc-scoreBoard__infoItem, .sc-scoreBoard__info",
        )

        # チーム名（2つの.sc-scoreBoard__teamNameまたはフォールバック）
        team_names = [
            el.get_text(strip=True)
            for el in soup.select(".sc-scoreBoard__teamName, .sc-scoreBoard__name")
            if el.get_text(strip=True)
        ]
        home_team = team_names[0] if len(team_names) > 0 else ""
        away_team = team_names[1] if len(team_names) > 1 else ""

        # スコア（Home / Away 合計スコア）
        home_score = self._get_text_by_selector(
            soup,
            ".sc-scoreBoard__data--totalHome",
        )
        away_score = self._get_text_by_selector(
            soup,
            ".sc-scoreBoard__data--totalAway",
        )
        score_total = f"{home_score} - {away_score}" if home_score and away_score else ""
        if not score_total:
            score_total = self._get_text_by_selector(
                soup,
                ".sc-scoreBoard__scoreTotal",
            )

        # 得点者情報の抽出
        home_scorers = self._parse_scorers(soup, ".sc-goalPlayer__list--home")
        away_scorers = self._parse_scorers(soup, ".sc-goalPlayer__list--away")

        return {
            "section": header_title,
            "datetime_venue": meta_info,
            "home_team": home_team,
            "away_team": away_team,
            "score": score_total,
            "home_scorers": home_scorers,
            "away_scorers": away_scorers,
        }

    def _get_text_by_selector(
        self,
        soup: BeautifulSoup,
        selector: str,
    ) -> str:
        """指定したセレクタに一致する要素のテキストを取得する."""
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else ""

    def _parse_scorers(
        self,
        soup: BeautifulSoup,
        selector: str,
    ) -> List[Dict[str, str]]:
        """得点者リストを抽出する."""
        scorers: List[Dict[str, str]] = []
        container = soup.select_one(selector)
        if not container:
            return scorers

        items = container.select(".sc-goalPlayer__listItem")
        for item in items:
            name_el = item.select_one(".sc-goalPlayer__name")
            time_el = item.select_one(".sc-goalPlayer__time")
            name = name_el.get_text(strip=True) if name_el else ""
            time_str = time_el.get_text(strip=True) if time_el else ""
            if name:
                scorers.append({
                    "player": name,
                    "time": time_str,
                })

        return scorers


    def _parse_team_stats(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """チームスタッツ比較表（sc-tableVersus）を抽出する."""
        table = soup.select_one("table.sc-tableVersus")
        if not table:
            return {}

        rows = table.find_all("tr")
        if not rows:
            return {}

        # チーム名の抽出 (Row 0: [HomeTeam, '', AwayTeam])
        first_row_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        home_team = first_row_cells[0] if len(first_row_cells) > 0 else "Home"
        away_team = first_row_cells[2] if len(first_row_cells) > 2 else "Away"

        stats_items: Dict[str, Dict[str, str]] = {}
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) == 3:
                home_val, stat_name, away_val = cells
                stats_items[stat_name] = {
                    home_team: home_val,
                    away_team: away_val,
                }

        return {
            "home_team": home_team,
            "away_team": away_team,
            "metrics": stats_items,
        }

    def _parse_player_stats(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """個人スタッツ表（sc-tablePlayerStats）を抽出する."""
        table = soup.select_one("table.sc-tablePlayerStats")
        if not table:
            return []

        rows = table.find_all("tr")
        if len(rows) < 3:
            return []

        # Row 0, 1 はヘッダー。Row 2以降が各選手の行
        players: List[Dict[str, Any]] = []
        for row in rows[2:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 34:
                continue

            player_data = self._build_player_dict(cells)
            players.append(player_data)

        return players

    def _build_player_dict(self, cells: List[str]) -> Dict[str, Any]:
        """34要素のセル配列から構造化された選手スタッツ辞書を生成する."""
        return {
            "position": cells[0],
            "player_name": cells[1],
            "team_name": cells[2],
            "attack": {
                "shoot": cells[3],
                "shoot_on_target": cells[4],
                "goals": cells[5],
                "dribble_success": cells[6],
            },
            "defense": {
                "tackle_success": cells[7],
                "loose_ball_recovery": cells[8],
                "block": cells[9],
                "clear": cells[10],
                "save_rate": cells[11],
            },
            "distance": {
                "total": cells[12],
                "first_half": cells[13],
                "second_half": cells[14],
            },
            "sprint": {
                "total": cells[15],
                "first_half": cells[16],
                "second_half": cells[17],
                "max_speed": cells[18],
            },
            "pass": {
                "pass_success": cells[19],
                "attacking_third_pass": cells[20],
                "through_pass": cells[21],
                "cross": cells[22],
                "assist": cells[23],
            },
            "plays_by_area": {
                "total": cells[24],
                "attacking_third": cells[25],
                "middle_third": cells[26],
                "defensive_third": cells[27],
            },
            "set_pieces": {
                "fk": cells[28],
                "ck": cells[29],
            },
            "discipline": {
                "yellow_card": cells[30],
                "red_card": cells[31],
                "foul": cells[32],
                "suffer_foul": cells[33],
            },
        }

    def _parse_text_timeline(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """テキスト速報のタイムラインアイテム（sc-textLive__item）を抽出する."""
        items = soup.select(".sc-textLive__item")
        timeline: List[Dict[str, Any]] = []

        for index, item in enumerate(items):
            entry = self._extract_timeline_item(item, index)
            if entry:
                timeline.append(entry)

        return timeline

    def _extract_timeline_item(
        self,
        item: Tag,
        index: int,
    ) -> Optional[Dict[str, Any]]:
        """単一のタイムライン要素から時間、チーム、テキストを抽出する."""
        time_el = item.select_one(".sc-textLive__status")
        team_el = item.select_one(".sc-textLive__name")
        text_el = item.select_one(".sc-textLive__text")

        time_str = time_el.get_text(strip=True) if time_el else ""
        team_str = team_el.get_text(strip=True) if team_el else None
        text_str = text_el.get_text(strip=True) if text_el else ""

        if not text_str and not time_str:
            return None

        # 重要イベント（ゴール等）の簡易フラグ付け（「ゴール期待値」等を除外）
        is_goal = bool(re.search(r"GO{2,}AL|(?<!期待値の)ゴール(?!期待値)|(?<!\w)得点", text_str))
        is_card = bool(re.search(r"警告|退場|イエロー|レッド", text_str))
        is_substitution = bool(re.search(r"交代|OUT|IN", text_str))


        return {
            "order": index,
            "time": time_str,
            "team": team_str,
            "text": text_str,
            "is_goal": is_goal,
            "is_card": is_card,
            "is_substitution": is_substitution,
        }
