"""
Match Context & Tactical Support Information Calculator (scripts/calculate_match_context.py).

Deterministically calculates:
1. Schedule, Rest Days (中何日), and Travel Burden
2. Disciplinary Status (Suspensions & Warning Reaches)
3. Weather, Pitch & Climate Conditions with Tactical Implications
4. Loan & Contractual Restrictions (期限付き移籍出場制限)

Pure deterministic Python calculation (Zero hallucination).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("match_context_calculator")

ROOT_DIR = Path(__file__).resolve().parent.parent


class MatchContextCalculator:
    """Calculates objective pre-match external context and constraints."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        stadium_config_path: Optional[Path] = None,
        loan_config_path: Optional[Path] = None,
        injury_config_path: Optional[Path] = None,
        raw_spaia_dir: Optional[Path] = None,
        markdown_dir: Optional[Path] = None,
    ) -> None:
        self.db_path = db_path or (ROOT_DIR / "data" / "football.db")
        self.stadium_config_path = stadium_config_path or (
            ROOT_DIR / "config" / "stadium_master.json"
        )
        self.loan_config_path = loan_config_path or (
            ROOT_DIR / "config" / "loan_restrictions.json"
        )
        self.injury_config_path = injury_config_path or (
            ROOT_DIR / "config" / "injury_tracker.json"
        )
        self.raw_spaia_dir = raw_spaia_dir or (
            ROOT_DIR / "data" / "raw" / "spaia"
        )
        self.markdown_dir = markdown_dir or (
            ROOT_DIR / "data" / "markdown" / "2026"
        )
        self.stadium_master = self._load_stadium_master()
        self.loan_master = self._load_loan_master()
        self.injury_master = self._load_injury_master()

    def _load_injury_master(self) -> List[Dict[str, Any]]:
        """Load injury tracker master configuration."""
        if not self.injury_config_path.exists():
            return []
        try:
            data = json.loads(self.injury_config_path.read_text(encoding="utf-8"))
            return data.get("injuries", [])
        except Exception as e:
            logger.warning("Failed to load injury tracker: %s", e)
            return []

    def _load_stadium_master(self) -> Dict[str, Any]:
        """Load stadium location and distance dictionary."""
        if not self.stadium_config_path.exists():
            return {}
        try:
            return json.loads(
                self.stadium_config_path.read_text(encoding="utf-8"),
            )
        except Exception as e:
            logger.warning("Failed to load stadium master: %s", e)
            return {}

    def _load_loan_master(self) -> List[Dict[str, Any]]:
        """Load loan player restriction configurations."""
        if not self.loan_config_path.exists():
            return []
        try:
            data = json.loads(self.loan_config_path.read_text(encoding="utf-8"))
            return data.get("loans", [])
        except Exception as e:
            logger.warning("Failed to load loan restrictions: %s", e)
            return []

    def _get_db_connection(self) -> Optional[sqlite3.Connection]:
        """Establish connection to SQLite database."""
        if not self.db_path.exists():
            return None
        return sqlite3.connect(str(self.db_path))

    # ==========================================
    # 1. 過密日程・中何日・移動負担 (Schedule & Fatigue)
    # ==========================================
    def calculate_schedule_fatigue(
        self,
        team_id: str,
        current_date_str: str,
        current_stadium: str,
        is_home: bool,
    ) -> Dict[str, Any]:
        """
        Calculate rest days (中何日), consecutive away fixtures,
        and travel distance from previous official match.
        """
        conn = self._get_db_connection()
        if not conn:
            return self._build_default_fatigue_dict()

        cur = conn.cursor()
        query = """
            SELECT match_id, date, home_team_id, away_team_id, stadium
            FROM matches
            WHERE (home_team_id = ? OR away_team_id = ?)
              AND date < ?
            ORDER BY date DESC
            LIMIT 1
        """
        row = cur.execute(
            query,
            (team_id, team_id, current_date_str),
        ).fetchone()
        conn.close()

        if not row:
            return {
                "previous_match_date": None,
                "days_between": None,
                "rest_days": None,
                "rest_days_display": "開幕戦 / 期間空き",
                "is_congested": False,
                "is_consecutive_away": False,
                "travel_distance_km": 0,
                "fatigue_risk_level": "LOW",
                "summary_text": "直近公式戦からの間隔は十分確保されています。",
            }

        prev_date_str = row[1]
        prev_home_team = row[2]
        prev_stadium = row[4] or ""

        try:
            cur_dt = datetime.strptime(current_date_str, "%Y-%m-%d")
            prev_dt = datetime.strptime(prev_date_str, "%Y-%m-%d")
            days_diff = (cur_dt - prev_dt).days
            rest_days = max(0, days_diff - 1)
        except Exception:
            days_diff = None
            rest_days = None

        # Check season opener (gap > 60 days)
        if days_diff is not None and days_diff > 60:
            return {
                "previous_match_date": prev_date_str,
                "days_between": days_diff,
                "rest_days": None,
                "rest_days_display": "シーズン開幕戦",
                "is_congested": False,
                "is_consecutive_away": False,
                "travel_distance_km": 0,
                "transit_type": "HOME",
                "fatigue_risk_level": "LOW",
                "summary_text": "シーズン開幕戦（プレシーズン調整期間を経て疲労懸念なし）。",
            }

        prev_is_away = prev_home_team != team_id
        is_consecutive_away = prev_is_away and (not is_home)

        # Travel distance lookup
        travel_distance_km = 0
        transit_type = "HOME"
        if not is_home:
            stadium_info = self.stadium_master.get(current_stadium, {})
            travel_distance_km = stadium_info.get("distance_from_tokyo_km", 0)
            transit_type = stadium_info.get("transit_type", "TRANSIT")

        is_congested = (rest_days is not None and rest_days <= 3)

        risk_level = "LOW"
        if rest_days is not None:
            if rest_days <= 2:
                risk_level = "EXTREME"
            elif rest_days <= 3 and (is_consecutive_away or travel_distance_km >= 300):
                risk_level = "HIGH"
            elif rest_days <= 3:
                risk_level = "MEDIUM"

        summary_parts = []
        if rest_days is not None:
            summary_parts.append(f"前節（{prev_date_str}）より中{rest_days}日の過密日程" if is_congested else f"前節より中{rest_days}日")
        if is_consecutive_away:
            summary_parts.append("アウェイ連戦")
        if travel_distance_km >= 200:
            summary_parts.append(f"遠征移動約{travel_distance_km}km（{transit_type}）")

        summary_text = "、".join(summary_parts) + ("。選手の筋疲労・後半運動量低下リスクに注意。" if is_congested else "。")

        return {
            "previous_match_date": prev_date_str,
            "days_between": days_diff,
            "rest_days": rest_days,
            "rest_days_display": f"中{rest_days}日" if rest_days is not None else "-",
            "is_congested": is_congested,
            "is_consecutive_away": is_consecutive_away,
            "travel_distance_km": travel_distance_km,
            "transit_type": transit_type,
            "fatigue_risk_level": risk_level,
            "summary_text": summary_text,
        }

    def _build_default_fatigue_dict(self) -> Dict[str, Any]:
        """Fallback empty fatigue dictionary."""
        return {
            "previous_match_date": None,
            "days_between": None,
            "rest_days": None,
            "rest_days_display": "-",
            "is_congested": False,
            "is_consecutive_away": False,
            "travel_distance_km": 0,
            "transit_type": "UNKNOWN",
            "fatigue_risk_level": "LOW",
            "summary_text": "日程データが取得できませんでした。",
        }

    # ==========================================
    # 2. 累積警告・出場停止情報 (Disciplinary Status)
    # ==========================================
    def calculate_disciplinary_status(
        self,
        team_id: str,
        current_date_str: str,
        spaia_team_id: int = 270,
    ) -> Dict[str, Any]:
        """
        Calculate cumulative yellow cards, players on yellow card reach (3 cards),
        and players suspended due to red cards in previous match.
        """
        # Read from raw SPAIA player stats files before current_date_str
        card_history_by_player: Dict[str, int] = {}
        suspended_due_to_red: List[str] = []
        warning_reach_players: List[Dict[str, Any]] = []

        # Find and deduplicate player stats files containing this team
        all_files = sorted(list(self.raw_spaia_dir.glob("*_player_stats.json")))
        
        team_matches: Dict[str, Tuple[str, List[Dict[str, Any]]]] = {}
        for p in all_files:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue

            game_id = str(data.get("game_id", ""))
            stats = data.get("player_stats", [])
            # Check if this team is in the match
            team_stats = [
                item for item in stats
                if item.get("TeamID") == spaia_team_id or str(item.get("TeamID")) == str(spaia_team_id)
            ]
            if not team_stats:
                continue

            # Determine match date from filename or stats
            m_date = re.search(r"(\d{4})(\d{2})(\d{2})", p.name)
            if not m_date:
                continue
            date_fmt = f"{m_date.group(1)}-{m_date.group(2)}-{m_date.group(3)}"

            if date_fmt >= current_date_str:
                continue

            # Key by date_fmt or game_id to deduplicate synonym files
            match_key = f"{date_fmt}_{game_id}" if game_id else date_fmt
            if match_key not in team_matches:
                team_matches[match_key] = (date_fmt, team_stats)

        # Sort matches chronologically by date
        sorted_matches = sorted(team_matches.values(), key=lambda x: x[0])

        last_match_reds: List[str] = []
        for idx, (m_date, team_stats) in enumerate(sorted_matches):
            match_reds: List[str] = []
            for item in team_stats:
                name = item.get("Name", "").replace("\u3000", " ").strip()
                if not name:
                    continue

                try:
                    y = int(item.get("Yellow") or 0)
                except (ValueError, TypeError):
                    y = 0
                try:
                    r = int(item.get("Red") or 0)
                except (ValueError, TypeError):
                    r = 0

                if y > 0:
                    card_history_by_player[name] = card_history_by_player.get(name, 0) + y
                if r > 0:
                    match_reds.append(name)

            if idx == len(sorted_matches) - 1:
                # The directly preceding match of THIS team
                last_match_reds = match_reds

        # Determine suspensions & reaches
        suspended_players = []
        # Red in last match => automatic suspension
        for p_name in last_match_reds:
            suspended_players.append({
                "player_name": p_name,
                "reason": "前節退場（一発レッドまたは警告2枚）に伴う自動出場停止",
                "type": "RED_SUSPENSION",
            })

        # Warning reaches (3 cards in season)
        for p_name, count in card_history_by_player.items():
            # J1 rule: 4 yellows = 1 match suspension
            curr_cycle = count % 4
            if curr_cycle == 3:
                warning_reach_players.append({
                    "player_name": p_name,
                    "cumulative_yellows": count,
                    "warning": "累積警告3枚（あと1枚で次節出場停止リーチ）",
                })

        summary_parts = []
        if suspended_players:
            names = ", ".join([sp["player_name"] for sp in suspended_players])
            summary_parts.append(f"【出場停止】{names}（前節退場）")
        if warning_reach_players:
            reach_names = ", ".join([f"{wp['player_name']}({wp['cumulative_yellows']}枚)" for wp in warning_reach_players])
            summary_parts.append(f"【警告リーチ】{reach_names}")

        summary_text = " / ".join(summary_parts) if summary_parts else "累積警告による出場停止・リーチ選手なし"

        return {
            "suspended_players": suspended_players,
            "warning_reach_players": warning_reach_players,
            "all_cumulative_yellows": card_history_by_player,
            "summary_text": summary_text,
        }

    # ==========================================
    # 3. 特殊なピッチ状態・気候条件 (Weather & Pitch)
    # ==========================================
    def calculate_weather_pitch_context(
        self,
        match_id: str,
    ) -> Dict[str, Any]:
        """
        Parse weather, temperature, humidity, and extract tactical implications
        (e.g., extreme heat, cooling break, slippery wet turf).
        """
        conn = self._get_db_connection()
        weather_raw = ""
        pitch_raw = ""
        stadium = ""
        if conn:
            cur = conn.cursor()
            row = cur.execute(
                "SELECT weather, pitch_condition, stadium FROM matches WHERE match_id = ?",
                (match_id,),
            ).fetchone()
            conn.close()
            if row:
                weather_raw = row[0] or ""
                pitch_raw = row[1] or ""
                stadium = row[2] or ""

        # Parse temperature and humidity
        # e.g., "天候:晴 / 気温:29.7℃ / 湿度:76%" or "天候:のち雨 / 気温:27.9℃ / 湿度:89%"
        temp_c: Optional[float] = None
        humidity_pct: Optional[int] = None
        weather_condition = "不明"

        m_temp = re.search(r"気温[:：]?\s*([0-9.]+)", weather_raw)
        if m_temp:
            try:
                temp_c = float(m_temp.group(1))
            except ValueError:
                pass

        m_hum = re.search(r"湿度[:：]?\s*([0-9]+)", weather_raw)
        if m_hum:
            try:
                humidity_pct = int(m_hum.group(1))
            except ValueError:
                pass

        m_weath = re.search(r"天候[:：]?\s*([^\s/℃%]+)", weather_raw)
        if m_weath:
            weather_condition = m_weath.group(1)
        elif "雨" in weather_raw:
            weather_condition = "雨"
        elif "晴" in weather_raw:
            weather_condition = "晴"
        elif "曇" in weather_raw:
            weather_condition = "曇"

        # Determine environmental risks
        is_extreme_heat = (temp_c is not None and temp_c >= 28.5) or (
            temp_c is not None and temp_c >= 27.0 and (humidity_pct or 0) >= 75
        )
        is_rain = "雨" in weather_condition or (humidity_pct is not None and humidity_pct >= 85)
        cooling_break = is_extreme_heat

        tactical_implications = []
        if is_extreme_heat:
            tactical_implications.append(
                f"気温{temp_c}℃・湿度{humidity_pct}%の酷暑環境。飲水・クーリングブレイク実施基準。ハイプレス強度の持続低下と後半60分以降の交代枠活用が勝敗を左右する。"
            )
        if is_rain:
            tactical_implications.append(
                "降雨・高湿度によるスリッピーなピッチ。ショートパスの前進事故リスクが高まり、ロングボール配給とセカンドボール回収への割り切りが有効。"
            )
        if not tactical_implications:
            tactical_implications.append(
                "良好な気候コンディション。通常通りの戦術プラン実行に適した環境。"
            )

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
            "cooling_break_required": cooling_break,
            "tactical_implications": " ".join(tactical_implications),
            "summary_text": summary_text,
        }

    # ==========================================
    # 4. 契約上の出場制限 (Loan Restrictions)
    # ==========================================
    def check_loan_restrictions(
        self,
        current_team_id: str,
        opponent_team_id: str,
    ) -> Dict[str, Any]:
        """
        Check if any players on current team are loaned from opponent team
        and restricted from playing by contract clauses.
        """
        restricted_players: List[Dict[str, Any]] = []

        for item in self.loan_master:
            c_team = item.get("current_team_id")
            p_club = item.get("parent_club_id")
            is_restricted = item.get("restricted_against_parent", True)

            if c_team == current_team_id and p_club == opponent_team_id and is_restricted:
                restricted_players.append({
                    "player_name": item.get("player_name"),
                    "player_id": item.get("player_id"),
                    "parent_club_id": p_club,
                    "parent_club_name": item.get("parent_club_name"),
                    "reason": f"所属元クラブ（{item.get('parent_club_name')}）との公式戦出場制限契約条項によるメンバー外",
                })

        summary_text = (
            f"契約上出場不可: {', '.join([rp['player_name'] for rp in restricted_players])}"
            if restricted_players
            else "所属元契約による出場制限なし"
        )

        return {
            "has_loan_restriction": len(restricted_players) > 0,
            "restricted_players": restricted_players,
            "summary_text": summary_text,
        }

    # ==========================================
    # 5. 怪我・コンディション情報 (Injury & Condition Context)
    # ==========================================
    def get_injury_condition_context(
        self,
        team_id: str,
        current_date_str: str,
        match_id: str,
    ) -> Dict[str, Any]:
        """
        Extract active injuries, players under minute restrictions,
        and quotes from coach interviews/reviews regarding condition.
        """
        active_injuries: List[Dict[str, Any]] = []
        for item in self.injury_master:
            if item.get("team_id") != team_id:
                continue

            diag_date = item.get("diagnosis_date", "2099-12-31")
            status = item.get("status", "ACTIVE")

            # Check if diagnosed on or before current match
            if diag_date <= current_date_str:
                active_injuries.append({
                    "player_name": item.get("player_name"),
                    "injury_type": item.get("injury_type"),
                    "expected_recovery": item.get("expected_recovery"),
                    "status": status,
                    "notes": item.get("notes", ""),
                })

        # Extract mentions from match review / coach interviews
        coach_mentions: List[str] = self._extract_injury_mentions_from_reviews(
            match_id=match_id,
        )

        summary_parts = []
        if active_injuries:
            names = ", ".join([f"{ai['player_name']}（{ai['injury_type']}）" for ai in active_injuries])
            summary_parts.append(f"【負傷離脱・調整】{names}")
        if coach_mentions:
            summary_parts.append(f"【監督・公式言及】{coach_mentions[0][:120]}...")

        summary_text = " / ".join(summary_parts) if summary_parts else "公式負傷離脱者なし"

        return {
            "active_injuries": active_injuries,
            "coach_mentions": coach_mentions,
            "summary_text": summary_text,
        }

    def _extract_injury_mentions_from_reviews(
        self,
        match_id: str,
    ) -> List[str]:
        """Extract injury or fatigue quotes from match markdown reports."""
        if not self.markdown_dir.exists():
            return []

        keywords = ["怪我", "負傷", "別メニュー", "違和感", "大事をとって", "離脱", "復帰", "制限"]
        mentions: List[str] = []

        for p in self.markdown_dir.glob(f"*{match_id}*.md"):
            try:
                content = p.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    clean = line.strip()
                    if any(k in clean for k in keywords):
                        if len(clean) > 20 and not clean.startswith("#"):
                            mentions.append(clean)
            except Exception as e:
                logger.warning("Failed to parse markdown for injury mentions: %s", e)

        return mentions

    # ==========================================
    # 6. 総合コンテキスト統合 (Full Match Context)
    # ==========================================
    def get_full_match_context(
        self,
        team_id: str,
        opponent_team_id: str,
        match_id: str,
        date_str: str,
        stadium: str,
        is_home: bool,
    ) -> Dict[str, Any]:
        """Aggregate all 5 external tactical context elements."""
        fatigue = self.calculate_schedule_fatigue(
            team_id=team_id,
            current_date_str=date_str,
            current_stadium=stadium,
            is_home=is_home,
        )
        disciplinary = self.calculate_disciplinary_status(
            team_id=team_id,
            current_date_str=date_str,
        )
        weather = self.calculate_weather_pitch_context(
            match_id=match_id,
        )
        loan = self.check_loan_restrictions(
            current_team_id=team_id,
            opponent_team_id=opponent_team_id,
        )
        injury = self.get_injury_condition_context(
            team_id=team_id,
            current_date_str=date_str,
            match_id=match_id,
        )

        return {
            "match_id": match_id,
            "team_id": team_id,
            "opponent_team_id": opponent_team_id,
            "schedule_fatigue": fatigue,
            "disciplinary": disciplinary,
            "weather_pitch": weather,
            "loan_restrictions": loan,
            "injury_condition": injury,
        }

    def calculate_context(
        self,
        match_id: str,
        team_id: str = "FCT",
    ) -> Dict[str, Any]:
        """Convenience method: auto-resolve match metadata from DB or ID and calculate context."""
        date_str = ""
        stadium = ""
        home_team_id = ""
        away_team_id = ""

        # Attempt to load from matches table in SQLite
        if self.db_path.exists():
            try:
                conn = sqlite3.connect(self.db_path)
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT date, stadium, home_team_id, away_team_id
                    FROM matches
                    WHERE match_id = ?
                    LIMIT 1;
                    """,
                    (match_id,),
                )
                row = cur.fetchone()
                conn.close()
                if row:
                    date_str = row[0] or ""
                    stadium = row[1] or ""
                    home_team_id = row[2] or ""
                    away_team_id = row[3] or ""
            except Exception as e:
                logger.warning("Could not query matches table for %s: %s", match_id, e)

        # Fallback resolution from match_id pattern (e.g., 20261025_FCT_MIT)
        if not date_str and len(match_id) >= 8 and match_id[:8].isdigit():
            raw_d = match_id[:8]
            date_str = f"{raw_d[:4]}-{raw_d[4:6]}-{raw_d[6:8]}"

        if not home_team_id or not away_team_id:
            parts = match_id.split("_")
            if len(parts) >= 3:
                home_team_id = parts[1]
                away_team_id = parts[2]

        is_home = (home_team_id == team_id) if home_team_id else True
        opponent_team_id = (
            away_team_id if is_home else home_team_id
        ) if (home_team_id and away_team_id) else ("MIT" if team_id == "FCT" else "FCT")

        if not stadium:
            stadium = "味の素スタジアム" if is_home else "アウェイスタジアム"

        return self.get_full_match_context(
            team_id=team_id,
            opponent_team_id=opponent_team_id,
            match_id=match_id,
            date_str=date_str,
            stadium=stadium,
            is_home=is_home,
        )
