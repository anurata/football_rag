"""2026年J1全20クラブ対応 連戦負荷・出場停止・試合コンテキスト決定論算出サービス (pipeline/match_context_service.py).

機能:
1. チーム休養日数（中何日）・過密日程・アウェイ連戦・全20クラブ対応の遠征移動距離算出
2. 選手別の直近累積出場負荷（直近3/5試合・直近14/21日間の分数・走行距離・スプリント・高負荷判定）
3. J1公式規約準拠の出場停止・警告リーチ算出（4枚累積停止＆次節消化リセット・警告2枚退場の累積非算入・前節退場停止）
4. 負傷離脱者・期限付き移籍の対戦制限契約条項・気象ピッチ条件の統合取得
5. 厳密な時系列リーク防止（指定試合日 `as_of_date` より前の公式戦データのみを参照）
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("match_context_service")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_STADIUM_PATH = ROOT_DIR / "config" / "stadium_master.json"
DEFAULT_LOAN_PATH = ROOT_DIR / "config" / "loan_restrictions.json"
DEFAULT_INJURY_PATH = ROOT_DIR / "config" / "injury_tracker.json"
DEFAULT_MARKDOWN_DIR = ROOT_DIR / "data" / "markdown" / "2026"

# 全20クラブ（＋主要Jクラブ）本拠地概算座標 (緯度, 経度)
CLUB_HOME_COORDS: Dict[str, Tuple[float, float]] = {
    "KAS": (35.9920, 140.6404),  # 鹿嶋
    "MIT": (36.3456, 140.4128),  # 水戸
    "URA": (35.9035, 139.7175),  # さいたま
    "JEF": (35.5775, 140.1228),  # 千葉
    "REY": (35.8486, 139.9753),  # 柏
    "FCT": (35.6643, 139.5272),  # 調布（東京）
    "VER": (35.6643, 139.5272),  # 東京
    "ZEL": (35.5925, 139.4386),  # 町田
    "KAW": (35.5858, 139.6525),  # 川崎
    "MAR": (35.5100, 139.6064),  # 横浜
    "PUL": (34.9847, 138.4811),  # 静岡（清水）
    "NAG": (35.0844, 137.1708),  # 豊田・名古屋
    "SAN": (35.0169, 135.5683),  # 亀岡・京都
    "GAM": (34.8028, 135.5381),  # 吹田
    "CER": (34.6142, 135.5169),  # 大阪長居
    "VOB": (34.6567, 135.1694),  # 神戸
    "VIS": (34.6567, 135.1694),  # 神戸互換
    "OKA": (34.6808, 133.9189),  # 岡山
    "HIR": (34.4014, 132.4547),  # 広島
    "FUK": (33.5858, 130.4606),  # 福岡
    "VVN": (32.7592, 129.8669),  # 長崎
    "BEL": (35.3436, 139.3414),  # 平塚
    "ALB": (37.8825, 139.0592),  # 新潟
    "SAG": (33.3717, 130.5203),  # 鳥栖
    "CON": (43.0150, 141.4097),  # 札幌
}


@dataclass
class _PlayerDisciplineState:
    """選手ごとのシーズン内カード・出場停止状態管理."""

    player_id: str
    player_name: str
    cumulative_yellows: int = 0
    pending_yellow_suspension: bool = False
    served_yellow_suspensions: int = 0


def _load_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read JSON %s: %s", path, exc)
        return {}


def _haversine_km(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """2地点の緯度経度から大圏距離 (km) を返す."""
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * (math.sin(dlon / 2.0) ** 2)
    )
    return 6371.0 * 2.0 * math.asin(min(1.0, math.sqrt(a)))


def _infer_transit_type(distance_km: int) -> str:
    """移動距離から標準交通手段を返す."""
    if distance_km <= 0:
        return "HOME"
    if distance_km <= 70:
        return "LOCAL_TRAIN"
    if distance_km <= 160:
        return "TRAIN"
    if distance_km <= 680:
        return "SHINKANSEN"
    if distance_km <= 850:
        return "SHINKANSEN_OR_FLIGHT"
    return "FLIGHT"


def _resolve_stadium_info(
    stadium_name: str,
    stadium_master: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """スタジアム名（完全一致または部分一致）からマスタ情報を引く."""
    if not stadium_name:
        return None
    if stadium_name in stadium_master:
        return stadium_master[stadium_name]
    for key, info in stadium_master.items():
        if key in stadium_name or stadium_name in key:
            return info
    return None


def estimate_club_travel(
    team_id: str,
    current_stadium: str,
    is_home: bool,
    stadium_master: Dict[str, Any],
) -> Tuple[int, str]:
    """任意のクラブのアウェイ移動距離(km)と移動手段を決定論算出する."""
    if is_home:
        return (0, "HOME")

    s_info = _resolve_stadium_info(current_stadium, stadium_master)
    if team_id == "FCT" and s_info is not None:
        return (
            int(s_info.get("distance_from_tokyo_km", 0)),
            str(s_info.get("transit_type", "TRANSIT")),
        )

    origin = CLUB_HOME_COORDS.get(team_id)
    dest_tid = s_info.get("team_id") if s_info else None
    dest = CLUB_HOME_COORDS.get(str(dest_tid)) if dest_tid else None

    if origin and dest:
        if origin == dest:
            return (15, "LOCAL_BUS")
        raw_km = _haversine_km(origin, dest) * 1.22
        rounded_km = int(round(raw_km / 10.0) * 10)
        return (max(10, rounded_km), _infer_transit_type(rounded_km))

    if s_info is not None:
        fallback_km = int(s_info.get("distance_from_tokyo_km", 0))
        return (fallback_km, str(s_info.get("transit_type", "TRANSIT")))

    return (0, "TRANSIT")


def _season_from_date(date_str: str) -> int:
    """YYYY-MM-DD 文字列から対象シーズン年（デフォルト2026）を抽出する."""
    if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return 2026


class MatchContextService:
    """全20クラブ対応の連戦負荷・出場停止・試合前提コンテキスト算出エンジン."""

    def __init__(
        self,
        db_path: Optional[Any] = None,
        stadium_config_path: Optional[Path] = None,
        loan_config_path: Optional[Path] = None,
        injury_config_path: Optional[Path] = None,
        markdown_dir: Optional[Path] = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.stadium_config_path = stadium_config_path or DEFAULT_STADIUM_PATH
        self.loan_config_path = loan_config_path or DEFAULT_LOAN_PATH
        self.injury_config_path = injury_config_path or DEFAULT_INJURY_PATH
        self.markdown_dir = markdown_dir or DEFAULT_MARKDOWN_DIR

        self.stadium_master: Dict[str, Any] = _load_json_dict(self.stadium_config_path)
        self.loan_master: List[Dict[str, Any]] = _load_json_dict(self.loan_config_path).get("loans", [])
        self.injury_master: List[Dict[str, Any]] = _load_json_dict(self.injury_config_path).get("injuries", [])

    def _connect(self) -> Optional[sqlite3.Connection]:
        if not self.db_path.exists():
            return None
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def resolve_match_or_date_target(
        self,
        team_id: str,
        match_id: Optional[str] = None,
        as_of_date: Optional[str] = None,
        matchweek: Optional[int] = None,
        season: int = 2026,
    ) -> Dict[str, Any]:
        """match_id / as_of_date / matchweek のいずれかから基準日と対戦メタ情報を解決する."""
        conn = self._connect()
        try:
            if conn and match_id:
                row = conn.execute(
                    """
                    SELECT match_id, season, matchweek, date, stadium, home_team_id, away_team_id
                    FROM matches
                    WHERE match_id = ?
                    LIMIT 1
                    """,
                    (match_id,),
                ).fetchone()
                if row:
                    return self._format_target_from_row(team_id, row)

            if conn and matchweek is not None and not as_of_date:
                row = conn.execute(
                    """
                    SELECT match_id, season, matchweek, date, stadium, home_team_id, away_team_id
                    FROM matches
                    WHERE season = ? AND matchweek = ?
                      AND (home_team_id = ? OR away_team_id = ?)
                    LIMIT 1
                    """,
                    (season, matchweek, team_id, team_id),
                ).fetchone()
                if row:
                    return self._format_target_from_row(team_id, row)

                max_prev = conn.execute(
                    """
                    SELECT MAX(date) FROM matches
                    WHERE season = ? AND matchweek < ?
                    """,
                    (season, matchweek),
                ).fetchone()
                inferred_date = "2026-10-31"
                if max_prev and max_prev[0]:
                    dt = datetime.strptime(max_prev[0], "%Y-%m-%d") + timedelta(days=6)
                    inferred_date = dt.strftime("%Y-%m-%d")
                as_of_date = inferred_date
        finally:
            if conn:
                conn.close()

        return self._fallback_target_metadata(team_id, match_id, as_of_date, season)

    def _format_target_from_row(self, team_id: str, row: sqlite3.Row) -> Dict[str, Any]:
        home_tid = row["home_team_id"] or ""
        away_tid = row["away_team_id"] or ""
        is_home = home_tid == team_id
        opp_tid = away_tid if is_home else home_tid
        return {
            "match_id": row["match_id"] or "",
            "season": int(row["season"] or 2026),
            "matchweek": row["matchweek"],
            "date_str": row["date"] or "",
            "stadium": row["stadium"] or "",
            "is_home": is_home,
            "opponent_team_id": opp_tid,
        }

    def _fallback_target_metadata(
        self,
        team_id: str,
        match_id: Optional[str],
        as_of_date: Optional[str],
        season: int,
    ) -> Dict[str, Any]:
        mid = match_id or ""
        date_str = as_of_date or ""
        if not date_str and len(mid) >= 8 and mid[:8].isdigit():
            date_str = f"{mid[:4]}-{mid[4:6]}-{mid[6:8]}"
        if not date_str:
            date_str = f"{season}-12-31"

        home_tid, away_tid = "", ""
        parts = mid.split("_")
        if len(parts) >= 3:
            home_tid, away_tid = parts[1], parts[2]

        is_home = (home_tid == team_id) if home_tid else True
        opp_tid = (away_tid if is_home else home_tid) if (home_tid and away_tid) else ""
        return {
            "match_id": mid,
            "season": _season_from_date(date_str),
            "matchweek": None,
            "date_str": date_str,
            "stadium": "",
            "is_home": is_home,
            "opponent_team_id": opp_tid,
        }

    def _fetch_prior_team_matches(
        self,
        conn: sqlite3.Connection,
        team_id: str,
        as_of_date: str,
        season: Optional[int] = None,
    ) -> List[sqlite3.Row]:
        """基準日より前の同一シーズン公式戦を時系列昇順で取得する（未来リーク厳禁）."""
        target_season = season or _season_from_date(as_of_date)
        return conn.execute(
            """
            SELECT match_id, season, matchweek, date, home_team_id, away_team_id, stadium
            FROM matches
            WHERE season = ?
              AND (home_team_id = ? OR away_team_id = ?)
              AND date < ?
            ORDER BY date ASC, match_id ASC
            """,
            (target_season, team_id, team_id, as_of_date),
        ).fetchall()

    # =========================================================================
    # 1. チーム休養日数・過密日程・移動負担 (Schedule & Fatigue)
    # =========================================================================
    def calculate_schedule_fatigue(
        self,
        team_id: str,
        current_date_str: str,
        current_stadium: str = "",
        is_home: bool = True,
    ) -> Dict[str, Any]:
        """直前公式戦からの休養日数（中何日）・連戦密度・移動距離を決定論算出する."""
        conn = self._connect()
        if not conn:
            return self._empty_fatigue_dict("日程データが取得できませんでした。")

        try:
            prior_matches = self._fetch_prior_team_matches(conn, team_id, current_date_str)
            if not prior_matches:
                # 別シーズン直近試合も一応確認し、60日超ならシーズン開幕戦表記を返す
                any_prev = conn.execute(
                    """
                    SELECT date, home_team_id, stadium
                    FROM matches
                    WHERE (home_team_id = ? OR away_team_id = ?) AND date < ?
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    (team_id, team_id, current_date_str),
                ).fetchone()
                if any_prev:
                    return self._build_season_opener_dict(any_prev["date"], current_date_str)
                return self._build_no_prior_match_dict()

            last_row = prior_matches[-1]
            return self._compute_fatigue_metrics(
                team_id=team_id,
                current_date_str=current_date_str,
                current_stadium=current_stadium,
                is_home=is_home,
                last_row=last_row,
                prior_matches=prior_matches,
            )
        finally:
            conn.close()

    def _compute_fatigue_metrics(
        self,
        team_id: str,
        current_date_str: str,
        current_stadium: str,
        is_home: bool,
        last_row: sqlite3.Row,
        prior_matches: List[sqlite3.Row],
    ) -> Dict[str, Any]:
        prev_date_str = str(last_row["date"])
        cur_dt = datetime.strptime(current_date_str, "%Y-%m-%d")
        prev_dt = datetime.strptime(prev_date_str, "%Y-%m-%d")
        days_diff = (cur_dt - prev_dt).days
        rest_days = max(0, days_diff - 1)

        if days_diff > 60:
            return self._build_season_opener_dict(prev_date_str, current_date_str)

        prev_is_away = last_row["home_team_id"] != team_id
        is_consecutive_away = prev_is_away and (not is_home)
        travel_km, transit_type = estimate_club_travel(
            team_id=team_id,
            current_stadium=current_stadium,
            is_home=is_home,
            stadium_master=self.stadium_master,
        )

        d14_cutoff = (cur_dt - timedelta(days=14)).strftime("%Y-%m-%d")
        d21_cutoff = (cur_dt - timedelta(days=21)).strftime("%Y-%m-%d")
        matches_14d = sum(1 for r in prior_matches if str(r["date"]) >= d14_cutoff)
        matches_21d = sum(1 for r in prior_matches if str(r["date"]) >= d21_cutoff)

        is_congested = rest_days <= 3
        risk_level = self._evaluate_fatigue_risk(
            rest_days=rest_days,
            is_consecutive_away=is_consecutive_away,
            travel_km=travel_km,
            matches_14d=matches_14d,
        )

        summary_parts = [
            f"前節（{prev_date_str}）より中{rest_days}日の過密日程"
            if is_congested
            else f"前節より中{rest_days}日",
        ]
        if is_consecutive_away:
            summary_parts.append("アウェイ連戦")
        if travel_km >= 200:
            summary_parts.append(f"遠征移動約{travel_km}km（{transit_type}）")

        suffix = "。選手の筋疲労・後半運動量低下リスクに注意。" if is_congested else "。"
        return {
            "previous_match_id": last_row["match_id"],
            "previous_match_date": prev_date_str,
            "days_between": days_diff,
            "rest_days": rest_days,
            "rest_days_display": f"中{rest_days}日",
            "matches_in_last_14d": matches_14d,
            "matches_in_last_21d": matches_21d,
            "is_congested": is_congested,
            "is_consecutive_away": is_consecutive_away,
            "travel_distance_km": travel_km,
            "transit_type": transit_type,
            "fatigue_risk_level": risk_level,
            "summary_text": "、".join(summary_parts) + suffix,
        }

    def _evaluate_fatigue_risk(
        self,
        rest_days: int,
        is_consecutive_away: bool,
        travel_km: int,
        matches_14d: int,
    ) -> str:
        if rest_days <= 2:
            return "EXTREME"
        if rest_days <= 3 and (is_consecutive_away or travel_km >= 300 or matches_14d >= 3):
            return "HIGH"
        if rest_days <= 3 or matches_14d >= 3:
            return "MEDIUM"
        return "LOW"

    def _build_season_opener_dict(self, prev_date_str: str, current_date_str: str) -> Dict[str, Any]:
        days_diff = (
            datetime.strptime(current_date_str, "%Y-%m-%d")
            - datetime.strptime(prev_date_str, "%Y-%m-%d")
        ).days
        return {
            "previous_match_id": None,
            "previous_match_date": prev_date_str,
            "days_between": days_diff,
            "rest_days": None,
            "rest_days_display": "シーズン開幕戦",
            "matches_in_last_14d": 0,
            "matches_in_last_21d": 0,
            "is_congested": False,
            "is_consecutive_away": False,
            "travel_distance_km": 0,
            "transit_type": "HOME",
            "fatigue_risk_level": "LOW",
            "summary_text": "シーズン開幕戦（プレシーズン調整期間を経て疲労懸念なし）。",
        }

    def _build_no_prior_match_dict(self) -> Dict[str, Any]:
        return {
            "previous_match_id": None,
            "previous_match_date": None,
            "days_between": None,
            "rest_days": None,
            "rest_days_display": "開幕戦 / 期間空き",
            "matches_in_last_14d": 0,
            "matches_in_last_21d": 0,
            "is_congested": False,
            "is_consecutive_away": False,
            "travel_distance_km": 0,
            "transit_type": "HOME",
            "fatigue_risk_level": "LOW",
            "summary_text": "直近公式戦からの間隔は十分確保されています。",
        }

    def _empty_fatigue_dict(self, msg: str) -> Dict[str, Any]:
        return {
            "previous_match_id": None,
            "previous_match_date": None,
            "days_between": None,
            "rest_days": None,
            "rest_days_display": "-",
            "matches_in_last_14d": 0,
            "matches_in_last_21d": 0,
            "is_congested": False,
            "is_consecutive_away": False,
            "travel_distance_km": 0,
            "transit_type": "UNKNOWN",
            "fatigue_risk_level": "LOW",
            "summary_text": msg,
        }

    # =========================================================================
    # 2. 選手別の直近累積出場負荷 (Player Cumulative Load)
    # =========================================================================
    def calculate_player_load(
        self,
        team_id: str,
        current_date_str: str,
    ) -> Dict[str, Any]:
        """基準日より前の公式戦から、選手ごとの直近3/5試合および14/21日間累積負荷を算出する."""
        conn = self._connect()
        if not conn:
            return {
                "prior_matches_count": 0,
                "high_load_players": [],
                "players": [],
                "summary_text": "出場負荷データなし",
            }

        try:
            prior_matches = self._fetch_prior_team_matches(conn, team_id, current_date_str)
            if not prior_matches:
                return {
                    "prior_matches_count": 0,
                    "high_load_players": [],
                    "players": [],
                    "summary_text": "開幕戦または直近出場履歴なし",
                }

            return self._aggregate_team_player_loads(
                conn=conn,
                team_id=team_id,
                current_date_str=current_date_str,
                prior_matches=prior_matches,
            )
        finally:
            conn.close()

    def _aggregate_team_player_loads(
        self,
        conn: sqlite3.Connection,
        team_id: str,
        current_date_str: str,
        prior_matches: List[sqlite3.Row],
    ) -> Dict[str, Any]:
        match_ids = [str(r["match_id"]) for r in prior_matches]
        match_dates = {str(r["match_id"]): str(r["date"]) for r in prior_matches}
        last_1_ids = set(match_ids[-1:])
        last_3_ids = set(match_ids[-3:])
        last_5_ids = set(match_ids[-5:])

        cur_dt = datetime.strptime(current_date_str, "%Y-%m-%d")
        cutoff_14d = (cur_dt - timedelta(days=14)).strftime("%Y-%m-%d")
        cutoff_21d = (cur_dt - timedelta(days=21)).strftime("%Y-%m-%d")

        placeholders = ",".join("?" for _ in match_ids)
        rows = conn.execute(
            f"""
            SELECT match_id, player_id, player_name, number, position,
                   is_starter, minutes_played, distance_km, sprints
            FROM player_match_stats
            WHERE team_id = ? AND match_id IN ({placeholders})
            """,
            [team_id, *match_ids],
        ).fetchall()

        acc: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            pid = str(r["player_id"])
            mid = str(r["match_id"])
            mdate = match_dates.get(mid, "")
            mins = int(r["minutes_played"] or 0)
            st = int(r["is_starter"] or 0)
            dist = float(r["distance_km"] or 0.0)
            spr = int(r["sprints"] or 0)

            entry = acc.setdefault(
                pid,
                {
                    "player_id": pid,
                    "player_name": str(r["player_name"] or ""),
                    "number": int(r["number"] or 0),
                    "position": str(r["position"] or ""),
                    "season_appearances": 0,
                    "season_starts": 0,
                    "season_minutes": 0,
                    "last_match_minutes": 0,
                    "minutes_last_3": 0,
                    "starts_last_3": 0,
                    "distance_km_last_3": 0.0,
                    "sprints_last_3": 0,
                    "minutes_last_5": 0,
                    "starts_last_5": 0,
                    "distance_km_last_5": 0.0,
                    "sprints_last_5": 0,
                    "minutes_last_14d": 0,
                    "minutes_last_21d": 0,
                },
            )
            if mins > 0:
                entry["season_appearances"] += 1
            entry["season_starts"] += st
            entry["season_minutes"] += mins

            if mid in last_1_ids:
                entry["last_match_minutes"] += mins
            if mid in last_3_ids:
                entry["minutes_last_3"] += mins
                entry["starts_last_3"] += st
                entry["distance_km_last_3"] = round(entry["distance_km_last_3"] + dist, 3)
                entry["sprints_last_3"] += spr
            if mid in last_5_ids:
                entry["minutes_last_5"] += mins
                entry["starts_last_5"] += st
                entry["distance_km_last_5"] = round(entry["distance_km_last_5"] + dist, 3)
                entry["sprints_last_5"] += spr
            if mdate >= cutoff_14d:
                entry["minutes_last_14d"] += mins
            if mdate >= cutoff_21d:
                entry["minutes_last_21d"] += mins

        players_list = list(acc.values())
        for p in players_list:
            m3 = p["minutes_last_3"]
            m14 = p["minutes_last_14d"]
            if m3 >= 240 or m14 >= 240:
                p["load_level"] = "HIGH"
            elif m3 >= 160 or m14 >= 160:
                p["load_level"] = "MEDIUM"
            else:
                p["load_level"] = "LOW"

        players_list.sort(
            key=lambda x: (x["minutes_last_3"], x["minutes_last_5"], x["season_minutes"]),
            reverse=True,
        )
        high_load = [
            p for p in players_list
            if p["load_level"] == "HIGH" and p["position"] != "GK"
        ]

        if high_load:
            top_desc = ", ".join(
                f"{p['player_name']}(直近3戦{p['minutes_last_3']}分)"
                for p in high_load[:5]
            )
            summary_text = f"【高負荷主力】{top_desc}"
        else:
            summary_text = "過度な連戦出場負荷（フィールド選手直近3戦240分以上）なし"

        return {
            "prior_matches_count": len(prior_matches),
            "high_load_players": high_load,
            "players": players_list,
            "summary_text": summary_text,
        }

    # =========================================================================
    # 3. 累積警告・出場停止情報 (Disciplinary Status - J1規約準拠)
    # =========================================================================
    def calculate_disciplinary_status(
        self,
        team_id: str,
        current_date_str: str,
    ) -> Dict[str, Any]:
        """J1規約に基づき、基準日時点の出場停止選手（退場／累積4枚）と警告リーチ（3枚）を決定論算出する."""
        conn = self._connect()
        if not conn:
            return self._empty_disciplinary_dict()

        try:
            prior_matches = self._fetch_prior_team_matches(conn, team_id, current_date_str)
            if not prior_matches:
                return self._empty_disciplinary_dict()

            return self._simulate_season_discipline(
                conn=conn,
                team_id=team_id,
                prior_matches=prior_matches,
            )
        finally:
            conn.close()

    def _simulate_season_discipline(
        self,
        conn: sqlite3.Connection,
        team_id: str,
        prior_matches: List[sqlite3.Row],
    ) -> Dict[str, Any]:
        match_ids = [str(r["match_id"]) for r in prior_matches]
        placeholders = ",".join("?" for _ in match_ids)
        rows = conn.execute(
            f"""
            SELECT match_id, player_id, player_name, raw_stats_json
            FROM player_match_stats
            WHERE team_id = ? AND match_id IN ({placeholders})
            """,
            [team_id, *match_ids],
        ).fetchall()

        rows_by_match: Dict[str, List[sqlite3.Row]] = {mid: [] for mid in match_ids}
        for r in rows:
            rows_by_match.setdefault(str(r["match_id"]), []).append(r)

        states: Dict[str, _PlayerDisciplineState] = {}
        last_match_reds: List[Tuple[str, str, int]] = []
        last_idx = len(match_ids) - 1

        for idx, mid in enumerate(match_ids):
            # 1. 前節までに累積4枚(8枚...)に達していた選手は、このチーム公式戦の経過をもって1試合停止を消化
            for st in states.values():
                if st.pending_yellow_suspension:
                    st.pending_yellow_suspension = False
                    st.served_yellow_suspensions += 1

            # 2. 当該試合でのカードイベント反映
            for r in rows_by_match.get(mid, []):
                pid = str(r["player_id"])
                pname = str(r["player_name"] or "").strip()
                if not pname:
                    continue
                yc, rc = self._extract_cards_from_raw_json(r["raw_stats_json"])
                if yc == 0 and rc == 0:
                    continue

                st = states.setdefault(
                    pid,
                    _PlayerDisciplineState(player_id=pid, player_name=pname),
                )
                st.player_name = pname

                if rc > 0:
                    if idx == last_idx:
                        last_match_reds.append((pid, pname, yc))
                    # Jリーグ規約: 警告2枚による退場(yc>=2, rc>=1)はその試合の退場停止に吸収され累積警告に算入しない
                    if yc == 1:
                        self._add_yellow_and_check_cycle(st, 1)
                elif yc > 0:
                    self._add_yellow_and_check_cycle(st, yc)

        return self._format_disciplinary_result(states, last_match_reds)

    def _extract_cards_from_raw_json(self, raw_json_str: Optional[str]) -> Tuple[int, int]:
        if not raw_json_str:
            return (0, 0)
        try:
            data = json.loads(raw_json_str)
            disc = data.get("discipline", {})
            yc = int(disc.get("yellow_cards") or 0)
            rc = int(disc.get("red_cards") or 0)
            return (yc, rc)
        except Exception:
            return (0, 0)

    def _add_yellow_and_check_cycle(self, st: _PlayerDisciplineState, added: int) -> None:
        prev_bucket = st.cumulative_yellows // 4
        st.cumulative_yellows += added
        new_bucket = st.cumulative_yellows // 4
        if st.cumulative_yellows > 0 and new_bucket > prev_bucket:
            st.pending_yellow_suspension = True

    def _format_disciplinary_result(
        self,
        states: Dict[str, _PlayerDisciplineState],
        last_match_reds: List[Tuple[str, str, int]],
    ) -> Dict[str, Any]:
        suspended_players: List[Dict[str, Any]] = []
        suspended_pids = set()

        for pid, pname, yc in last_match_reds:
            suspended_pids.add(pid)
            reason = (
                "前節退場（警告2枚による退場）に伴う自動出場停止"
                if yc >= 2
                else "前節退場（一発レッド）に伴う自動出場停止"
            )
            suspended_players.append(
                {
                    "player_id": pid,
                    "player_name": pname,
                    "reason": reason,
                    "type": "RED_SUSPENSION",
                },
            )

        for pid, st in states.items():
            if st.pending_yellow_suspension and pid not in suspended_pids:
                suspended_pids.add(pid)
                suspended_players.append(
                    {
                        "player_id": pid,
                        "player_name": st.player_name,
                        "cumulative_yellows": st.cumulative_yellows,
                        "reason": f"累積警告{st.cumulative_yellows}枚到達に伴う今節出場停止",
                        "type": "YELLOW_ACCUMULATION_SUSPENSION",
                    },
                )

        warning_reach_players: List[Dict[str, Any]] = []
        all_yellows: Dict[str, int] = {}
        for pid, st in states.items():
            if st.cumulative_yellows > 0:
                all_yellows[st.player_name] = st.cumulative_yellows
            if pid in suspended_pids:
                continue
            if st.cumulative_yellows % 4 == 3:
                warning_reach_players.append(
                    {
                        "player_id": pid,
                        "player_name": st.player_name,
                        "cumulative_yellows": st.cumulative_yellows,
                        "warning": f"累積警告{st.cumulative_yellows}枚（あと1枚で次節出場停止リーチ）",
                    },
                )

        summary_parts: List[str] = []
        if suspended_players:
            s_desc = ", ".join(
                f"{sp['player_name']}（{'累積警告' if sp['type'] == 'YELLOW_ACCUMULATION_SUSPENSION' else '前節退場'}）"
                for sp in suspended_players
            )
            summary_parts.append(f"【出場停止】{s_desc}")
        if warning_reach_players:
            r_desc = ", ".join(
                f"{wp['player_name']}({wp['cumulative_yellows']}枚)"
                for wp in warning_reach_players
            )
            summary_parts.append(f"【警告リーチ】{r_desc}")

        summary_text = (
            " / ".join(summary_parts)
            if summary_parts
            else "累積警告・退場による出場停止・リーチ選手なし"
        )
        return {
            "suspended_players": suspended_players,
            "warning_reach_players": warning_reach_players,
            "all_cumulative_yellows": all_yellows,
            "summary_text": summary_text,
        }

    def _empty_disciplinary_dict(self) -> Dict[str, Any]:
        return {
            "suspended_players": [],
            "warning_reach_players": [],
            "all_cumulative_yellows": {},
            "summary_text": "累積警告・退場による出場停止・リーチ選手なし",
        }

    # =========================================================================
    # 4. 気象・ピッチ環境 / 移籍制限 / 負傷コンディション
    # =========================================================================
    def calculate_weather_pitch_context(self, match_id: str) -> Dict[str, Any]:
        """試合の天候・気温・湿度をパースし、戦術的含意を決定論付与する."""
        weather_raw = ""
        if match_id:
            conn = self._connect()
            if conn:
                try:
                    row = conn.execute(
                        "SELECT weather FROM matches WHERE match_id = ?",
                        (match_id,),
                    ).fetchone()
                    if row:
                        weather_raw = str(row["weather"] or "")
                finally:
                    conn.close()

        temp_c: Optional[float] = None
        humidity_pct: Optional[int] = None
        weather_condition = "不明"

        m_temp = re.search(r"気温[:：]?\s*([0-9.]+)", weather_raw)
        if m_temp:
            temp_c = float(m_temp.group(1))
        m_hum = re.search(r"湿度[:：]?\s*([0-9]+)", weather_raw)
        if m_hum:
            humidity_pct = int(m_hum.group(1))
        m_weath = re.search(r"天候[:：]?\s*([^\s/℃%]+)", weather_raw)
        if m_weath:
            weather_condition = m_weath.group(1)
        elif "雨" in weather_raw:
            weather_condition = "雨"
        elif "晴" in weather_raw:
            weather_condition = "晴"
        elif "曇" in weather_raw:
            weather_condition = "曇"

        is_extreme_heat = (temp_c is not None and temp_c >= 28.5) or (
            temp_c is not None and temp_c >= 27.0 and (humidity_pct or 0) >= 75
        )
        is_rain = "雨" in weather_condition or (humidity_pct is not None and humidity_pct >= 85)

        implications: List[str] = []
        if is_extreme_heat:
            implications.append(
                f"気温{temp_c}℃・湿度{humidity_pct}%の酷暑環境。飲水・クーリングブレイク実施基準。"
                "ハイプレス強度の持続低下と後半60分以降の交代枠活用が勝敗を左右する。",
            )
        if is_rain:
            implications.append(
                "降雨・高湿度によるスリッピーなピッチ。ショートパスの前進事故リスクが高まり、"
                "ロングボール配給とセカンドボール回収への割り切りが有効。",
            )
        if not implications:
            implications.append("良好な気候コンディション。通常通りの戦術プラン実行に適した環境。")

        summary_text = f"【気候】{weather_condition} (気温: {temp_c or '-'}℃ / 湿度: {humidity_pct or '-'}%)"
        if is_extreme_heat:
            summary_text += " [酷暑警戒/飲水タイム]"
        if is_rain:
            summary_text += " [雨天重馬場/スリッピー]"

        return {
            "weather_condition": weather_condition,
            "temperature_c": temp_c,
            "humidity_percent": humidity_pct,
            "is_extreme_heat": is_extreme_heat,
            "is_rain_slippery": is_rain,
            "cooling_break_required": is_extreme_heat,
            "tactical_implications": " ".join(implications),
            "summary_text": summary_text,
        }

    def check_loan_restrictions(
        self,
        current_team_id: str,
        opponent_team_id: str,
    ) -> Dict[str, Any]:
        """対戦相手が期限付き移籍元クラブである場合の出場制限条項対象選手を返す."""
        restricted: List[Dict[str, Any]] = []
        for item in self.loan_master:
            if (
                item.get("current_team_id") == current_team_id
                and item.get("parent_club_id") == opponent_team_id
                and item.get("restricted_against_parent", True)
            ):
                p_name = item.get("parent_club_name", opponent_team_id)
                restricted.append(
                    {
                        "player_name": item.get("player_name"),
                        "player_id": item.get("player_id"),
                        "parent_club_id": opponent_team_id,
                        "parent_club_name": p_name,
                        "reason": f"所属元クラブ（{p_name}）との公式戦出場制限契約条項によるメンバー外",
                    },
                )

        summary_text = (
            f"契約上出場不可: {', '.join(str(r['player_name']) for r in restricted)}"
            if restricted
            else "所属元契約による出場制限なし"
        )
        return {
            "has_loan_restriction": len(restricted) > 0,
            "restricted_players": restricted,
            "summary_text": summary_text,
        }

    def get_injury_condition_context(
        self,
        team_id: str,
        current_date_str: str,
        match_id: str = "",
    ) -> Dict[str, Any]:
        """基準日以前に登録された負傷離脱者および公式レビュー言及を返す."""
        active_injuries: List[Dict[str, Any]] = []
        for item in self.injury_master:
            if item.get("team_id") != team_id:
                continue
            status = item.get("status", "ACTIVE")
            if status not in ("OUT", "INJURED", "RECOVERING"):
                continue
            diag_date = str(item.get("diagnosis_date", "2099-12-31"))
            if diag_date <= current_date_str:
                active_injuries.append(
                    {
                        "player_name": item.get("player_name"),
                        "injury_type": item.get("injury_type"),
                        "expected_recovery": item.get("expected_recovery"),
                        "status": status,
                        "notes": item.get("notes", ""),
                    },
                )

        coach_mentions = self._extract_injury_mentions_from_reviews(match_id) if match_id else []
        parts: List[str] = []
        if active_injuries:
            names = ", ".join(f"{ai['player_name']}（{ai['injury_type']}）" for ai in active_injuries)
            parts.append(f"【負傷離脱・調整】{names}")
        if coach_mentions:
            parts.append(f"【監督・公式言及】{coach_mentions[0][:120]}...")

        return {
            "active_injuries": active_injuries,
            "coach_mentions": coach_mentions,
            "summary_text": " / ".join(parts) if parts else "公式負傷離脱者なし",
        }

    def _extract_injury_mentions_from_reviews(self, match_id: str) -> List[str]:
        if not match_id or not self.markdown_dir.exists():
            return []
        keywords = ("怪我", "負傷", "別メニュー", "違和感", "大事をとって", "離脱", "復帰", "制限")
        mentions: List[str] = []
        for p in self.markdown_dir.glob(f"*{match_id}*.md"):
            try:
                for raw_line in p.read_text(encoding="utf-8").split("\n"):
                    clean = raw_line.strip()
                    if len(clean) > 20 and not clean.startswith("#") and any(k in clean for k in keywords):
                        mentions.append(clean)
            except Exception as exc:
                logger.warning("Failed to parse markdown %s: %s", p, exc)
        return mentions

    # =========================================================================
    # 5. 順位表・直近先発メンバー（Layer 1 確定事実）
    # =========================================================================
    def calculate_league_standings(
        self,
        season: int = 2026,
        as_of_date: str = "2026-12-31",
    ) -> Dict[str, Any]:
        """指定日時点の同一シーズン全試合結果から決定論的順位表を算出する."""
        conn = self._connect()
        if not conn:
            return {"table": [], "by_team": {}}

        try:
            rows = conn.execute(
                """
                SELECT home_team_id, away_team_id, home_score, away_score
                FROM matches
                WHERE season = ? AND date < ? AND home_score IS NOT NULL
                """,
                (season, as_of_date),
            ).fetchall()

            table_dict: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                ht, at = str(r["home_team_id"]), str(r["away_team_id"])
                hs, as_ = int(r["home_score"]), int(r["away_score"])
                for tid in (ht, at):
                    table_dict.setdefault(
                        tid,
                        {
                            "team_id": tid,
                            "points": 0,
                            "matches_played": 0,
                            "wins": 0,
                            "draws": 0,
                            "losses": 0,
                            "goals_for": 0,
                            "goals_against": 0,
                            "goal_difference": 0,
                        },
                    )

                table_dict[ht]["matches_played"] += 1
                table_dict[at]["matches_played"] += 1
                table_dict[ht]["goals_for"] += hs
                table_dict[ht]["goals_against"] += as_
                table_dict[at]["goals_for"] += as_
                table_dict[at]["goals_against"] += hs

                if hs > as_:
                    table_dict[ht]["points"] += 3
                    table_dict[ht]["wins"] += 1
                    table_dict[at]["losses"] += 1
                elif hs < as_:
                    table_dict[at]["points"] += 3
                    table_dict[at]["wins"] += 1
                    table_dict[ht]["losses"] += 1
                else:
                    table_dict[ht]["points"] += 1
                    table_dict[at]["points"] += 1
                    table_dict[ht]["draws"] += 1
                    table_dict[at]["draws"] += 1

            for st in table_dict.values():
                st["goal_difference"] = st["goals_for"] - st["goals_against"]

            sorted_list = sorted(
                table_dict.values(),
                key=lambda x: (x["points"], x["goal_difference"], x["goals_for"]),
                reverse=True,
            )

            leader_pts = sorted_list[0]["points"] if sorted_list else 0
            for rank_idx, item in enumerate(sorted_list, start=1):
                item["rank"] = rank_idx
                item["points_from_leader"] = leader_pts - item["points"]

            by_team = {item["team_id"]: item for item in sorted_list}
            return {
                "season": season,
                "as_of_date": as_of_date,
                "table": sorted_list,
                "by_team": by_team,
            }
        finally:
            conn.close()

    def get_recent_lineup_and_scorers(
        self,
        team_id: str,
        current_date_str: str,
    ) -> Dict[str, Any]:
        """直前試合の実先発11人・ベンチメンバーおよび直近3戦の得点者を決定論抽出する."""
        conn = self._connect()
        if not conn:
            return {"last_match_id": None, "starters": [], "bench": [], "recent_scorers": []}

        try:
            prior_matches = self._fetch_prior_team_matches(conn, team_id, current_date_str)
            if not prior_matches:
                return {"last_match_id": None, "starters": [], "bench": [], "recent_scorers": []}

            last_match = prior_matches[-1]
            last_mid = str(last_match["match_id"])
            last_date = str(last_match["date"])

            # 直前試合の出場メンバー
            p_rows = conn.execute(
                """
                SELECT pms.player_id, pms.player_name, pms.number, pms.position,
                       pms.is_starter, pms.minutes_played, pms.goals,
                       emp.dominant_foot,
                       pmp.primary_role, pmp.primary_lane
                FROM player_match_stats pms
                LEFT JOIN entity_master_players emp ON pms.player_id = emp.player_id
                LEFT JOIN player_match_positions pmp ON pms.match_id = pmp.match_id AND pms.player_id = pmp.player_id
                WHERE pms.match_id = ? AND pms.team_id = ?
                ORDER BY pms.is_starter DESC, pms.minutes_played DESC, pms.number ASC
                """,
                (last_mid, team_id),
            ).fetchall()

            starters = []
            bench = []
            for r in p_rows:
                p_item = {
                    "player_id": r["player_id"],
                    "player_name": r["player_name"],
                    "number": r["number"],
                    "position": r["position"],
                    "primary_role": r["primary_role"] or "",
                    "primary_lane": r["primary_lane"] or "",
                    "is_starter": bool(r["is_starter"]),
                    "minutes_played": r["minutes_played"],
                    "dominant_foot": r["dominant_foot"],
                    "goals_in_match": r["goals"],
                }
                if r["is_starter"]:
                    starters.append(p_item)
                else:
                    bench.append(p_item)

            # 直近3戦の得点者
            last_3_mids = [str(m["match_id"]) for m in prior_matches[-3:]]
            placeholders = ",".join("?" for _ in last_3_mids)
            scorer_rows = conn.execute(
                f"""
                SELECT player_id, player_name, number, SUM(goals) AS total_goals
                FROM player_match_stats
                WHERE team_id = ? AND match_id IN ({placeholders}) AND goals > 0
                GROUP BY player_id
                ORDER BY total_goals DESC
                """,
                [team_id, *last_3_mids],
            ).fetchall()

            recent_scorers = [
                {
                    "player_id": r["player_id"],
                    "player_name": r["player_name"],
                    "number": r["number"],
                    "goals_last_3": r["total_goals"],
                }
                for r in scorer_rows
            ]

            return {
                "last_match_id": last_mid,
                "last_match_date": last_date,
                "starters": starters,
                "bench": bench,
                "recent_scorers": recent_scorers,
            }
        finally:
            conn.close()

    # =========================================================================
    # 6. 統合API (試合ID指定 / クラブ＋日付・節指定 プレビュー対応)
    # =========================================================================
    def get_club_prematch_context(
        self,
        team_id: str,
        match_id: Optional[str] = None,
        as_of_date: Optional[str] = None,
        matchweek: Optional[int] = None,
        opponent_team_id: Optional[str] = None,
        stadium: Optional[str] = None,
        is_home: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """任意のクラブ・試合・節・日付時点における連戦負荷・出場停止・順位・直近スタメンを一括取得する."""
        meta = self.resolve_match_or_date_target(
            team_id=team_id,
            match_id=match_id,
            as_of_date=as_of_date,
            matchweek=matchweek,
        )
        eff_mid = match_id if match_id is not None else meta["match_id"]
        eff_date = as_of_date if as_of_date is not None else meta["date_str"]
        eff_opp = opponent_team_id if opponent_team_id is not None else meta["opponent_team_id"]
        eff_stad = stadium if stadium is not None else meta["stadium"]
        eff_home = is_home if is_home is not None else meta["is_home"]

        standings = self.calculate_league_standings(
            season=meta["season"],
            as_of_date=eff_date,
        )
        team_standing = standings["by_team"].get(team_id, {})
        opp_standing = standings["by_team"].get(eff_opp, {}) if eff_opp else {}

        return {
            "match_id": eff_mid,
            "matchweek": meta["matchweek"] if matchweek is None else matchweek,
            "as_of_date": eff_date,
            "team_id": team_id,
            "opponent_team_id": eff_opp,
            "standings": {
                "team": team_standing,
                "opponent": opp_standing,
                "table_top_5": standings["table"][:5],
            },
            "recent_lineup": self.get_recent_lineup_and_scorers(
                team_id=team_id,
                current_date_str=eff_date,
            ),
            "schedule_fatigue": self.calculate_schedule_fatigue(
                team_id=team_id,
                current_date_str=eff_date,
                current_stadium=eff_stad,
                is_home=eff_home,
            ),
            "player_load": self.calculate_player_load(
                team_id=team_id,
                current_date_str=eff_date,
            ),
            "disciplinary": self.calculate_disciplinary_status(
                team_id=team_id,
                current_date_str=eff_date,
            ),
            "weather_pitch": self.calculate_weather_pitch_context(eff_mid),
            "loan_restrictions": self.check_loan_restrictions(
                current_team_id=team_id,
                opponent_team_id=eff_opp,
            ),
            "injury_condition": self.get_injury_condition_context(
                team_id=team_id,
                current_date_str=eff_date,
                match_id=eff_mid,
            ),
        }

    def get_matchup_prematch_context(self, match_id: str) -> Dict[str, Any]:
        """1試合の両チーム（Home / Away）双方の連戦負荷・出場停止・休養日数差を一括取得する."""
        conn = self._connect()
        if not conn:
            raise ValueError(f"Database not found: {self.db_path}")
        try:
            row = conn.execute(
                "SELECT home_team_id, away_team_id, date, stadium, matchweek FROM matches WHERE match_id = ?",
                (match_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            raise ValueError(f"Match not found: {match_id}")

        home_tid = str(row["home_team_id"])
        away_tid = str(row["away_team_id"])
        date_str = str(row["date"])
        stadium = str(row["stadium"] or "")
        mw = row["matchweek"]

        home_ctx = self.get_club_prematch_context(
            team_id=home_tid,
            match_id=match_id,
            as_of_date=date_str,
            matchweek=mw,
            opponent_team_id=away_tid,
            stadium=stadium,
            is_home=True,
        )
        away_ctx = self.get_club_prematch_context(
            team_id=away_tid,
            match_id=match_id,
            as_of_date=date_str,
            matchweek=mw,
            opponent_team_id=home_tid,
            stadium=stadium,
            is_home=False,
        )

        h_rest = home_ctx["schedule_fatigue"].get("rest_days")
        a_rest = away_ctx["schedule_fatigue"].get("rest_days")
        rest_diff = (h_rest - a_rest) if (h_rest is not None and a_rest is not None) else 0

        return {
            "match_id": match_id,
            "matchweek": mw,
            "date": date_str,
            "home_team_id": home_tid,
            "away_team_id": away_tid,
            "rest_days_advantage_home": rest_diff,
            "home": home_ctx,
            "away": away_ctx,
        }

