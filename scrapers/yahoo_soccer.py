"""Yahoo!サッカー（sports.yahoo.co.jp / soccer.yahoo.co.jp）のデータスクレイパー.

Jリーグの試合スタッツ（チームスタッツ、個人スタッツ）および
テキスト速報タイムラインを取得・パースしてJSON保存する.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


def parse_yahoo_minute_label(label: str) -> int:
    """Yahooの時間ラベル（例: '前半0分', '後半18分'）を通算分（0〜90+）に変換する."""
    cleaned = label.strip()
    m_first = re.search(r"前半(\d+)", cleaned)
    if m_first:
        return min(int(m_first.group(1)), 45)
    m_second = re.search(r"後半(\d+)", cleaned)
    if m_second:
        return 45 + int(m_second.group(1))
    m_num = re.search(r"(\d+)", cleaned)
    if m_num:
        return int(m_num.group(1))
    return 0


def _classify_df_line(
    item: Dict[str, Any],
    line_count: int,
    formation: str,
) -> Tuple[str, str, str]:
    """DF列（-129 <= x <= -85）の選手に (role, role_group, lane) を割り当てる."""
    y = item["y"]
    is_three_back = formation.startswith("3-")
    is_five_back = formation.startswith("5-")

    if is_five_back or line_count >= 5:
        if y >= 55:
            return ("RWB", "WB", "RIGHT")
        if y <= -55:
            return ("LWB", "WB", "LEFT")

    if not is_three_back and (line_count == 4 or abs(y) >= 60):
        if y >= 55:
            return ("RSB", "FB", "RIGHT")
        if y <= -55:
            return ("LSB", "FB", "LEFT")

    if y > 15:
        return ("RCB", "CB", "RIGHT_HALF" if is_three_back else "CENTER")
    if y < -15:
        return ("LCB", "CB", "LEFT_HALF" if is_three_back else "CENTER")
    return ("CCB", "CB", "CENTER")


def _classify_deep_mf_line(
    item: Dict[str, Any],
    formation: str,
) -> Tuple[str, str, str]:
    """後列MF（-84 <= x <= -62）の選手に (role, role_group, lane) を割り当てる."""
    y = item["y"]
    is_three_back = formation.startswith("3-")
    if y >= 60:
        return ("RWB" if is_three_back else "RSH", "WB" if is_three_back else "WIDE_ATT", "RIGHT")
    if y <= -60:
        return ("LWB" if is_three_back else "LSH", "WB" if is_three_back else "WIDE_ATT", "LEFT")
    if y > 12:
        return ("RDMF", "DMF", "CENTER")
    if y < -12:
        return ("LDMF", "DMF", "CENTER")
    return ("DMF", "DMF", "CENTER")


def _classify_mid_mf_line(
    item: Dict[str, Any],
    has_deeper_mf: bool,
    formation: str,
) -> Tuple[str, str, str]:
    """中列MF（-61 <= x <= -45）の選手に (role, role_group, lane) を割り当てる."""
    y = item["y"]
    is_three_back = formation.startswith("3-")
    if y >= 55:
        return ("RWB" if is_three_back else "RSH", "WB" if is_three_back else "WIDE_ATT", "RIGHT")
    if y <= -55:
        return ("LWB" if is_three_back else "LSH", "WB" if is_three_back else "WIDE_ATT", "LEFT")

    group = "CMF" if has_deeper_mf else "DMF"
    prefix_r = "RCMF" if has_deeper_mf else "RDMF"
    prefix_l = "LCMF" if has_deeper_mf else "LDMF"
    center_role = "CMF" if has_deeper_mf else "DMF"

    if y > 12:
        return (prefix_r, group, "CENTER")
    if y < -12:
        return (prefix_l, group, "CENTER")
    return (center_role, group, "CENTER")


def _classify_am_line(
    item: Dict[str, Any],
    line_count: int,
    fwd_count: int,
) -> Tuple[str, str, str]:
    """2列目（-44 <= x <= -22）の選手に (role, role_group, lane) を割り当てる."""
    y = item["y"]
    # 4-2-3-1 等の2列目3枚（y=44, 0, -44）は両端をサイドハーフ/ウイング扱い
    if line_count >= 3 and abs(y) >= 35:
        if y > 0:
            return ("RSH", "WIDE_ATT", "RIGHT")
        return ("LSH", "WIDE_ATT", "LEFT")

    if abs(y) >= 55:
        return ("RWG" if y > 0 else "LWG", "WIDE_ATT", "RIGHT" if y > 0 else "LEFT")

    # 4-1-2-3 のように最前線が3枚いる場合はインサイドハーフ
    if fwd_count >= 3:
        if y > 10:
            return ("RCMF", "CMF", "RIGHT_HALF")
        if y < -10:
            return ("LCMF", "CMF", "LEFT_HALF")
        return ("CMF", "CMF", "CENTER")

    if y > 10:
        return ("RST", "SHADOW", "RIGHT_HALF")
    if y < -10:
        return ("LST", "SHADOW", "LEFT_HALF")
    return ("OMF", "SHADOW", "CENTER")


def _classify_fw_line(item: Dict[str, Any]) -> Tuple[str, str, str]:
    """最前線（x >= -21）の選手に (role, role_group, lane) を割り当てる."""
    y = item["y"]
    if y >= 50:
        return ("RWG", "WIDE_ATT", "RIGHT")
    if y <= -50:
        return ("LWG", "WIDE_ATT", "LEFT")
    if y > 10:
        return ("RCF", "CF", "CENTER")
    if y < -10:
        return ("LCF", "CF", "CENTER")
    return ("CF", "CF", "CENTER")


def infer_panel_tactical_roles(
    items: List[Dict[str, Any]],
    formation: str,
) -> List[Dict[str, Any]]:
    """1チーム1時間帯のピッチ座標リストに戦術ロール (inferred_role, role_group, inferred_lane) を付与する."""
    df_items = [it for it in items if -129 <= it["x"] <= -85]
    deep_mf_items = [it for it in items if -84 <= it["x"] <= -62]
    am_items = [it for it in items if -44 <= it["x"] <= -22]
    fw_items = [it for it in items if it["x"] >= -21]

    enriched: List[Dict[str, Any]] = []
    for it in items:
        x = it["x"]
        if x <= -130:
            role, group, lane = ("GK", "GK", "CENTER")
        elif -129 <= x <= -85:
            role, group, lane = _classify_df_line(it, len(df_items), formation)
        elif -84 <= x <= -62:
            role, group, lane = _classify_deep_mf_line(it, formation)
        elif -61 <= x <= -45:
            role, group, lane = _classify_mid_mf_line(it, bool(deep_mf_items), formation)
        elif -44 <= x <= -22:
            role, group, lane = _classify_am_line(it, len(am_items), len(fw_items))
        else:
            role, group, lane = _classify_fw_line(it)

        copied = dict(it)
        copied["inferred_role"] = role
        copied["role_group"] = group
        copied["inferred_lane"] = lane
        enriched.append(copied)

    return enriched


class YahooSoccerScraper:
    """Yahoo!サッカーのスタッツ・テキスト速報スクレイパー."""

    BASE_URL = "https://soccer.yahoo.co.jp/jleague/category/j1/game"
    SCHEDULE_URL = "https://soccer.yahoo.co.jp/jleague/category/j1/schedule/"

    def __init__(self, headers: Optional[Dict[str, str]] = None) -> None:
        """スクレイパーを初期化する."""
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    def fetch_schedule_game_ids(
        self,
        start_mw: int = 1,
        end_mw: int = 38,
        competition_id: Optional[str] = None,
    ) -> Dict[int, List[str]]:
        """Yahoo!サッカーの日程ページから各節の10桁game_id一覧を取得する."""
        comp_id = competition_id or self._detect_competition_id()
        result: Dict[int, List[str]] = {}
        if not comp_id:
            return result

        for mw in range(start_mw, end_mw + 1):
            url = f"https://soccer.yahoo.co.jp/jleague/category/j1/schedule/{comp_id}/{mw}/?gk=2"
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.encoding = "utf-8"
            resp.raise_for_status()
            gids = sorted(set(re.findall(r"/jleague/(?:category/j1/)?game/(\d{10})", resp.text)))
            result[mw] = gids

        return result

    def _detect_competition_id(self) -> Optional[str]:
        """J1日程トップから現在の大会ID（例: '31467'）を動的に検出する."""
        resp = requests.get(self.SCHEDULE_URL, headers=self.headers, timeout=15)
        resp.encoding = "utf-8"
        resp.raise_for_status()
        matches = re.findall(r"/jleague/category/j1/schedule/(\d+)/\d+/", resp.text)
        return matches[0] if matches else None

    def fetch_summary(self, game_id: str) -> Dict[str, Any]:
        """指定されたgame_idの出場メンバー・フォーメーション(/summary)を取得・解析する."""
        url = f"{self.BASE_URL}/{game_id}/summary"
        resp = requests.get(url, headers=self.headers, timeout=15)
        resp.encoding = "utf-8"
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        scoreboard = self._parse_scoreboard(soup)
        report_text = self._parse_summary_report(soup)
        lineup = self._parse_summary_lineup(soup)
        snapshots = self._parse_formation_snapshots(soup, lineup)

        return {
            "game_id": game_id,
            "url": url,
            "match_info": scoreboard,
            "report_text": report_text,
            "lineup": lineup,
            "formation_snapshots": snapshots,
        }

    def save_summary_data(
        self,
        game_id: str,
        output_dir: str = "data/raw/yahoo",
        save_game_id: Optional[str] = None,
    ) -> str:
        """出場メンバー・時間帯別フォーメーション図を取得してJSON保存する."""
        os.makedirs(output_dir, exist_ok=True)
        target_id = save_game_id or game_id
        summary_data = self.fetch_summary(game_id)
        summary_path = os.path.join(output_dir, f"{target_id}_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        return summary_path

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
        save_game_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """スタッツとテキスト速報を取得し、JSONファイルとして保存する.

        Args:
            game_id: 取得元試合ID
            output_dir: 出力先ディレクトリ
            save_game_id: 保存ファイル名に使用する試合ID (指定時はこちらで保存)

        Returns:
            保存したファイルパスの辞書
        """
        os.makedirs(output_dir, exist_ok=True)
        target_id = save_game_id or game_id

        stats_data = self.fetch_stats(game_id)
        text_data = self.fetch_text_live(game_id)

        stats_path = os.path.join(output_dir, f"{target_id}_stats.json")
        text_path = os.path.join(output_dir, f"{target_id}_text.json")

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

    # -------------------------------------------------------------------------
    # 出場メンバー・時間帯別フォーメーション図 (/summary) パースメソッド群
    # -------------------------------------------------------------------------

    def _parse_summary_report(self, soup: BeautifulSoup) -> str:
        """/summary内の戦評テキストを抽出する."""
        for header in soup.select(".sc-head01"):
            if "戦評" not in header.get_text(strip=True):
                continue
            parent = header.parent
            if not parent:
                continue
            full_txt = parent.get_text(" ", strip=True)
            return re.sub(r"^戦評\s*", "", full_txt).strip()
        return ""

    def _parse_summary_lineup(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """先発・ベンチメンバー表と監督名を抽出し、背番号→フルネーム対応も構築する."""
        member_tables: List[List[Dict[str, str]]] = []
        manager_names: List[str] = []

        for tbl in soup.select("table.sc-tableSplits"):
            rows = tbl.find_all("tr")
            if not rows:
                continue
            head_txt = " ".join(c.get_text(strip=True) for c in rows[0].find_all(["th", "td"]))
            if "背番号" in head_txt and "選手名" in head_txt:
                member_tables.append(self._parse_member_split_table(rows[1:]))
            elif head_txt == "監督名" and len(rows) >= 2:
                manager_names.append(rows[1].get_text(strip=True))

        home_starters = member_tables[0] if len(member_tables) >= 1 else []
        away_starters = member_tables[1] if len(member_tables) >= 2 else []
        home_bench = member_tables[2] if len(member_tables) >= 3 else []
        away_bench = member_tables[3] if len(member_tables) >= 4 else []

        return {
            "home": {
                "manager": manager_names[0] if len(manager_names) >= 1 else "",
                "starters": home_starters,
                "bench": home_bench,
                "roster_by_number": {
                    p["number"]: p["player_name"] for p in [*home_starters, *home_bench] if p.get("number")
                },
            },
            "away": {
                "manager": manager_names[1] if len(manager_names) >= 2 else "",
                "starters": away_starters,
                "bench": away_bench,
                "roster_by_number": {
                    p["number"]: p["player_name"] for p in [*away_starters, *away_bench] if p.get("number")
                },
            },
        }

    def _parse_member_split_table(self, data_rows: List[Tag]) -> List[Dict[str, str]]:
        """rowspan付きのメンバー表（Pos., 背番号, 選手名, 交代）を平坦なリストへ変換する."""
        players: List[Dict[str, str]] = []
        current_pos = ""
        for row in data_rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) >= 4:
                current_pos = cells[0]
                num, name, sub_info = cells[1], cells[2], cells[3]
            elif len(cells) == 3:
                num, name, sub_info = cells[0], cells[1], cells[2]
            else:
                continue
            players.append(
                {
                    "registered_pos": current_pos,
                    "number": num,
                    "player_name": name,
                    "sub_info": sub_info,
                },
            )
        return players

    def _parse_formation_snapshots(
        self,
        soup: BeautifulSoup,
        lineup: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """時間帯ごとのフォーメーション推移と全選手の(x, y)座標・推論ロールを抽出する."""
        form_sec = soup.select_one(".sc-formation")
        if not form_sec:
            return []

        time_labels = [el.get_text(strip=True) for el in form_sec.select(".js-changeTime")]
        home_forms = [
            el.get_text(strip=True)
            for el in form_sec.select(".sc-formation__team--home .js-changeFormation")
        ]
        away_forms = [
            el.get_text(strip=True)
            for el in form_sec.select(".sc-formation__team--away .js-changeFormation")
        ]

        panel_back = form_sec.select_one(".sc-formation__panelBack")
        if not panel_back:
            return []

        home_panels = panel_back.select(".sc-formation__panel--home")
        away_panels = panel_back.select(".sc-formation__panel--away")
        snap_count = min(len(home_panels), len(away_panels))

        home_roster = lineup.get("home", {}).get("roster_by_number", {})
        away_roster = lineup.get("away", {}).get("roster_by_number", {})

        snapshots: List[Dict[str, Any]] = []
        for idx in range(snap_count):
            t_label = time_labels[idx] if idx < len(time_labels) else ("前半0分" if idx == 0 else "")
            h_form = home_forms[idx] if idx < len(home_forms) else (home_forms[0] if home_forms else "")
            a_form = away_forms[idx] if idx < len(away_forms) else (away_forms[0] if away_forms else "")

            h_items = self._parse_single_formation_panel(home_panels[idx], home_roster, h_form)
            a_items = self._parse_single_formation_panel(away_panels[idx], away_roster, a_form)

            snapshots.append(
                {
                    "snapshot_index": idx,
                    "time_label": t_label,
                    "minute_approx": parse_yahoo_minute_label(t_label),
                    "home_formation": h_form,
                    "away_formation": a_form,
                    "home_players": h_items,
                    "away_players": a_items,
                },
            )
        return snapshots

    def _parse_single_formation_panel(
        self,
        panel: Tag,
        roster_by_number: Dict[str, str],
        formation: str,
    ) -> List[Dict[str, Any]]:
        """単一チームの1スナップショットパネルから座標・選手・戦術ロールを抽出する."""
        raw_items: List[Dict[str, Any]] = []
        for item in panel.select(".sc-formation__item"):
            x_val, y_val = self._extract_item_coords(item)
            num_el = item.select_one(".sc-formation__itemNumber")
            name_el = item.select_one(".sc-formation__itemName:not(.sc-formation__itemName--out)")
            out_el = item.select_one(".sc-formation__itemName--out")
            player_el = item.select_one(".sc-formation__itemPlayer")

            num = num_el.get_text(strip=True) if num_el else ""
            short_name = name_el.get_text(strip=True) if name_el else ""
            out_name = out_el.get_text(strip=True) if out_el else ""
            raw_text = player_el.get_text(" ", strip=True) if player_el else ""
            reg_pos_match = re.match(r"^(GK|DF|MF|FW)\b", raw_text)
            reg_pos = reg_pos_match.group(1) if reg_pos_match else ""

            raw_items.append(
                {
                    "number": num,
                    "short_name": short_name,
                    "player_name": roster_by_number.get(num, short_name),
                    "registered_pos": reg_pos,
                    "x": x_val,
                    "y": y_val,
                    "replaced_out_name": out_name,
                },
            )

        return infer_panel_tactical_roles(raw_items, formation)

    def _extract_item_coords(self, item: Tag) -> Tuple[int, int]:
        """sc-formation__item--x-101 sc-formation__item--y-33 等のクラス名から整数座標を抽出する."""
        x_val = 0
        y_val = 0
        for cls in item.get("class", []):
            mx = re.match(r"^sc-formation__item--x(-?\d+)$", cls)
            if mx:
                x_val = int(mx.group(1))
            my = re.match(r"^sc-formation__item--y(-?\d+)$", cls)
            if my:
                y_val = int(my.group(1))
        return (x_val, y_val)
