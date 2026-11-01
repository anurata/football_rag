"""2026年J1全20クラブ対応 スタメン予想＆選手交代シミュレーションサービス (pipeline/lineup_prediction_service.py).

機能:
1. 厳格な現所属ホワイトリスト制（entity_master_players WHERE team_id = ? に存在する選手のみを母集団とし、昔の選手や他クラブ選手の混入を100%遮断）
2. ハード制約除外（前節退場・累積4枚出場停止、期限付き移籍対戦制限、公式負傷離脱）
3. 確率論的スコアリング（直前節先発・交代時間、中何日・連戦負荷、直近得点・好調度、相手戦術相性・高さ）
4. 出力仕様:
   - 各ポジションの本命選手を表示
   - 25%以上の確率を持つ有力対抗馬が存在する場合は「本命選手（対抗: 〇〇 30%）」の形式で提示
5. 想定される交代プラン（時間帯・投入候補・交代理由・戦術的狙い）の自動生成
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from pipeline.match_context_service import MatchContextService

logger = logging.getLogger("lineup_prediction_service")

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "football.db"
DEFAULT_PROFILES_PATH = ROOT_DIR / "knowledge" / "team_tactical_profiles.json"


@dataclass
class PositionCandidate:
    """ポジション別候補選手の確率情報."""

    player_id: str
    player_name: str
    number: int
    registered_pos: str
    dominant_foot: Optional[str]
    height_cm: Optional[float]
    probability: float
    score: float
    notes: List[str]


@dataclass
class SlotPrediction:
    """1つのポジションスロットの予想結果."""

    slot_id: str
    slot_name: str
    primary: PositionCandidate
    contender: Optional[PositionCandidate] = None
    all_candidates: Optional[List[PositionCandidate]] = None


# フォーメーション別標準スロット定義
FORMATION_SLOTS: Dict[str, List[Tuple[str, str, str]]] = {
    "4-4-2": [
        ("GK", "GK", "GK"),
        ("RSB", "右サイドバック", "DF"),
        ("RCB", "右センターバック", "DF"),
        ("LCB", "左センターバック", "DF"),
        ("LSB", "左サイドバック", "DF"),
        ("RSH", "右サイドハーフ", "MF"),
        ("RCH", "右ボランチ", "MF"),
        ("LCH", "左ボランチ", "MF"),
        ("LSH", "左サイドハーフ", "MF"),
        ("RCF", "センターフォワード(右)", "FW"),
        ("LCF", "センターフォワード(左)", "FW"),
    ],
    "4-2-1-3": [
        ("GK", "GK", "GK"),
        ("RSB", "右サイドバック", "DF"),
        ("RCB", "右センターバック", "DF"),
        ("LCB", "左センターバック", "DF"),
        ("LSB", "左サイドバック", "DF"),
        ("RDM", "右ボランチ", "MF"),
        ("LDM", "左ボランチ", "MF"),
        ("OMF", "トップ下", "MF"),
        ("RWG", "右ウイング", "FW"),
        ("LWG", "左ウイング", "FW"),
        ("CF", "センターフォワード", "FW"),
    ],
    "4-2-3-1": [
        ("GK", "GK", "GK"),
        ("RSB", "右サイドバック", "DF"),
        ("RCB", "右センターバック", "DF"),
        ("LCB", "左センターバック", "DF"),
        ("LSB", "左サイドバック", "DF"),
        ("RDM", "右ボランチ", "MF"),
        ("LDM", "左ボランチ", "MF"),
        ("RSH", "右サイドハーフ", "MF"),
        ("OMF", "トップ下", "MF"),
        ("LSH", "左サイドハーフ", "MF"),
        ("CF", "センターフォワード", "FW"),
    ],
    "4-1-2-3": [
        ("GK", "GK", "GK"),
        ("RSB", "右サイドバック", "DF"),
        ("RCB", "右センターバック", "DF"),
        ("LCB", "左センターバック", "DF"),
        ("LSB", "左サイドバック", "DF"),
        ("ANCHOR", "アンカー", "MF"),
        ("RIH", "右インサイドハーフ", "MF"),
        ("LIH", "左インサイドハーフ", "MF"),
        ("RWG", "右ウイング", "FW"),
        ("LWG", "左ウイング", "FW"),
        ("CF", "センターフォワード", "FW"),
    ],
    "3-4-2-1": [
        ("GK", "GK", "GK"),
        ("RCB", "右センターバック", "DF"),
        ("CCB", "中央センターバック", "DF"),
        ("LCB", "左センターバック", "DF"),
        ("RWB", "右ウイングバック", "MF"),
        ("RCH", "右ボランチ", "MF"),
        ("LCH", "左ボランチ", "MF"),
        ("LWB", "左ウイングバック", "MF"),
        ("RST", "右シャドー", "FW"),
        ("LST", "左シャドー", "FW"),
        ("CF", "センターフォワード", "FW"),
    ],
    "3-4-1-2": [
        ("GK", "GK", "GK"),
        ("RCB", "右センターバック", "DF"),
        ("CCB", "中央センターバック", "DF"),
        ("LCB", "左センターバック", "DF"),
        ("RWB", "右ウイングバック", "MF"),
        ("RCH", "右ボランチ", "MF"),
        ("LCH", "左ボランチ", "MF"),
        ("LWB", "左ウイングバック", "MF"),
        ("OMF", "トップ下", "MF"),
        ("RCF", "センターフォワード(右)", "FW"),
        ("LCF", "センターフォワード(左)", "FW"),
    ],
}


class LineupPredictionService:
    """全20クラブ対応の決定論的スタメン予想＆交代シミュレーションエンジン."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        context_service: Optional[MatchContextService] = None,
        profiles_path: Optional[Path] = None,
    ) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.context_service = context_service or MatchContextService(db_path=self.db_path)
        self.profiles_path = profiles_path or DEFAULT_PROFILES_PATH
        self.team_profiles = self._load_team_profiles()

    def _load_team_profiles(self) -> Dict[str, Any]:
        if not self.profiles_path.exists():
            return {}
        try:
            data = json.loads(self.profiles_path.read_text(encoding="utf-8"))
            return data.get("teams", {})
        except Exception as exc:
            logger.warning("Failed to load team profiles: %s", exc)
            return {}

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # =========================================================================
    # 1. 現所属ホワイトリスト取得（他クラブ選手・過去選手の完全遮断）
    # =========================================================================
    def get_club_active_roster_whitelist(self, team_id: str) -> List[Dict[str, Any]]:
        """entity_master_players から指定クラブの現登録選手のみを厳格に取得する."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT
                    emp.player_id,
                    emp.team_id,
                    emp.number,
                    emp.canonical_name,
                    emp.position,
                    emp.height_cm,
                    emp.weight_kg,
                    emp.dominant_foot,
                    emp.profile_json,
                    pmp.primary_role,
                    COUNT(pms.match_id) AS total_matches
                FROM entity_master_players emp
                LEFT JOIN player_match_stats pms ON emp.player_id = pms.player_id
                LEFT JOIN (
                    SELECT player_id, primary_role
                    FROM player_match_positions
                    GROUP BY player_id
                ) pmp ON emp.player_id = pmp.player_id
                WHERE emp.team_id = ?
                GROUP BY emp.player_id
                ORDER BY emp.number ASC, emp.player_id ASC
                """,
                (team_id,),
            ).fetchall()

            roster: List[Dict[str, Any]] = []
            for r in rows:
                p_json = {}
                if r["profile_json"]:
                    try:
                        p_json = json.loads(r["profile_json"])
                    except Exception:
                        pass

                roster.append(
                    {
                        "player_id": r["player_id"],
                        "team_id": r["team_id"],
                        "number": r["number"] or 0,
                        "canonical_name": r["canonical_name"],
                        "position": r["position"] or "",
                        "primary_role": r["primary_role"] or "",
                        "total_matches": r["total_matches"] or 0,
                        "height_cm": float(r["height_cm"]) if r["height_cm"] else None,
                        "weight_kg": float(r["weight_kg"]) if r["weight_kg"] else None,
                        "dominant_foot": r["dominant_foot"],
                        "archetypes": p_json.get("archetypes", {}),
                    },
                )
            return roster
        finally:
            conn.close()

    # =========================================================================
    # 2. ハード制約判定（出場不可選手の完全除外）
    # =========================================================================
    def get_unavailable_player_ids(
        self,
        team_id: str,
        opponent_team_id: str,
        as_of_date: str,
    ) -> Set[str]:
        """出場停止、契約制限、公式負傷離脱者の player_id 集合を返す."""
        unavailable: Set[str] = set()

        # 出場停止
        disc = self.context_service.calculate_disciplinary_status(
            team_id=team_id,
            current_date_str=as_of_date,
        )
        for sp in disc.get("suspended_players", []):
            if sp.get("player_id"):
                unavailable.add(sp["player_id"])

        # 契約制限
        loans = self.context_service.check_loan_restrictions(
            current_team_id=team_id,
            opponent_team_id=opponent_team_id,
        )
        for rp in loans.get("restricted_players", []):
            if rp.get("player_id"):
                unavailable.add(rp["player_id"])

        # 負傷離脱（完全離脱 OUT のみ除外。時間制限調整中は残す）
        injuries = self.context_service.get_injury_condition_context(
            team_id=team_id,
            current_date_str=as_of_date,
        )
        roster = self.get_club_active_roster_whitelist(team_id)
        name_to_id = {p["canonical_name"]: p["player_id"] for p in roster}

        for ai in injuries.get("active_injuries", []):
            status = ai.get("status", "ACTIVE")
            p_name = ai.get("player_name", "")
            pid = name_to_id.get(p_name)
            if pid and status in ("OUT", "INJURED", "RECOVERING"):
                unavailable.add(pid)

        return unavailable

    # =========================================================================
    # 3. 候補選手のスコアリング計算
    # =========================================================================
    def _calculate_candidate_score(
        self,
        player: Dict[str, Any],
        slot_id: str,
        slot_group: str,
        recent_lineup: Dict[str, Any],
        fatigue: Dict[str, Any],
        player_load: Dict[str, Any],
        opp_profile: Dict[str, Any],
    ) -> Tuple[float, List[str]]:
        """1人の選手に対する特定スロットの適合スコアと理由タグを算出する."""
        score = 0.0
        notes: List[str] = []
        pid = player["player_id"]
        pos = player["position"].upper()
        arch = player.get("archetypes", {})
        prim_arch = arch.get("primary", "")

        # 1. ポジション適合度（基礎点）
        pos_fit = self._match_position_suitability(
            reg_pos=pos,
            slot_id=slot_id,
            slot_group=slot_group,
            primary_role=player.get("primary_role", ""),
            dominant_foot=player.get("dominant_foot"),
        )
        if pos_fit <= 0:
            return (0.0, [])
        score += pos_fit

        # 2. 直前節の出場実績
        starters = {p["player_id"]: p for p in recent_lineup.get("starters", [])}
        bench = {p["player_id"]: p for p in recent_lineup.get("bench", [])}

        if pid in starters:
            st_info = starters[pid]
            prev_role = (st_info.get("primary_role") or st_info.get("position") or "").upper()

            # 前節の役割・ポジションが、現在のスロットと合致しているか判定
            is_pos_match = False
            if slot_group == "GK" and "GK" in prev_role:
                is_pos_match = True
            elif "CB" in slot_id and any(k in prev_role for k in ("CB", "CCB", "RCB", "LCB")):
                is_pos_match = True
            elif ("SB" in slot_id or "WB" in slot_id) and any(k in prev_role for k in ("SB", "WB", "RSB", "LSB", "RWB", "LWB")):
                is_pos_match = True
            elif any(k in slot_id for k in ("CH", "DM", "ANCHOR", "VO")) and any(k in prev_role for k in ("DMF", "CMF", "VO", "DM", "CH", "ANCHOR", "RDMF", "LDMF")):
                is_pos_match = True
            elif any(k in slot_id for k in ("SH", "WG", "ST", "OMF")) and any(k in prev_role for k in ("SMF", "WG", "LWG", "RWG", "OMF", "SH", "ST", "RSH", "LSH")):
                is_pos_match = True
            elif any(k in slot_id for k in ("CF", "LCF", "RCF")) and any(k in prev_role for k in ("CF", "ST", "FW", "LCF", "RCF")):
                is_pos_match = True

            if is_pos_match:
                score += 55.0
                notes.append("前節先発")
                mins = st_info.get("minutes_played", 90)
                if mins <= 65:
                    score += 5.0
                    notes.append("前節早期交代・体力十分")
                score += 10.0  # ポジション継続ボーナス
            else:
                score += 15.0
                notes.append(f"前節他ポジション({prev_role})先発")
        elif pid in bench:
            score += 15.0
            notes.append("前節ベンチ")
            b_info = bench[pid]
            if b_info.get("goals_in_match", 0) > 0:
                score += 15.0
                notes.append(f"前節途中出場から得点({b_info['goals_in_match']}点)")

        # 3. 直近好調度およびシーズン通算実績
        for sc in recent_lineup.get("recent_scorers", []):
            if sc["player_id"] == pid:
                g_count = sc.get("goals_last_3", 0)
                score += min(g_count * 6.0, 18.0)
                notes.append(f"直近3戦{g_count}得点")

        # 4. 利き足と左右レーンの適合度
        foot_str = str(player.get("dominant_foot") or "")
        is_left_foot = "左" in foot_str
        is_right_foot = "右" in foot_str or "両" in foot_str

        if "LSB" in slot_id or "LWB" in slot_id:
            if is_left_foot:
                score += 25.0
                notes.append("左利きLSB/LWB適性")
            elif is_right_foot:
                score -= 10.0
        elif "RSB" in slot_id or "RWB" in slot_id:
            if is_right_foot:
                score += 15.0
            elif is_left_foot:
                score -= 30.0

        # 4. 連戦負荷・疲労による減点（中3日以下）
        rest_days = fatigue.get("rest_days")
        is_congested = fatigue.get("is_congested", False)
        load_map = {p["player_id"]: p for p in player_load.get("players", [])}
        p_load = load_map.get(pid, {})
        mins_last_3 = p_load.get("minutes_last_3", 0)

        if is_congested and mins_last_3 >= 240 and pos != "GK":
            score -= 22.0
            notes.append("過密日程・連戦高負荷")
        elif is_congested and mins_last_3 <= 90:
            score += 12.0
            notes.append("過密日程のフレッシュ要員")

        # 5. 対戦相手対策・ミスマッチ適性
        opp_base_f = opp_profile.get("base_formation", "")
        opp_is_5back = opp_base_f.startswith("3") or opp_base_f.startswith("5")

        if opp_is_5back and slot_group in ("FW", "MF"):
            if prim_arch in ("touchline_winger", "pocket_infiltrator", "line_breaker"):
                score += 10.0
                notes.append("5バック攻略適性(大外/裏抜け)")

        # 相手CBの高さ対策（立田191cm等）
        if slot_group == "FW" and prim_arch == "target_man":
            h = player.get("height_cm") or 0.0
            if h >= 185.0:
                score += 12.0
                notes.append(f"大型CB対策の基準点({int(h)}cm)")

        return (max(score, 0.0), notes)

    def _match_position_suitability(
        self,
        reg_pos: str,
        slot_id: str,
        slot_group: str,
        primary_role: str = "",
        dominant_foot: Optional[str] = None,
    ) -> float:
        """登録ポジション、実績ロール、利き足とスロットの一致度（0〜60点、不適正は0点）."""
        p_role = (primary_role or "").upper()
        reg = reg_pos.upper()

        foot_str = str(dominant_foot or "")
        is_left = "左" in foot_str
        is_right = "右" in foot_str or "両" in foot_str

        if slot_group == "GK":
            return 60.0 if "GK" in reg else 0.0

        # GK以外でGK登録選手は除外
        if "GK" in reg:
            return 0.0

        if slot_group == "DF":
            # FW専門・純粋アタッカーはDFスロットに入れない
            if any(k in p_role for k in ("CF", "ST", "FW", "LWG", "RWG")):
                return 0.0
            if "FW" in reg and not any(k in p_role for k in ("CB", "SB", "WB")):
                return 0.0

            if "CB" in slot_id:
                is_pure_sb = any(k in p_role for k in ("SB", "WB", "RSB", "LSB", "RWB", "LWB")) and not any(k in p_role for k in ("CB", "CCB", "RCB", "LCB"))
                if is_pure_sb:
                    return 0.0
                if any(k in p_role for k in ("CB", "RCB", "LCB", "CCB")):
                    return 60.0
                if "CB" in reg:
                    return 55.0
                if "DF" in reg and not is_pure_sb:
                    return 45.0
                return 0.0  # CB実績もDF適性もない選手は0点

            if "SB" in slot_id or "WB" in slot_id:
                # 純粋CBはSB/WBに配置しない
                is_pure_cb = any(k in p_role for k in ("CB", "CCB", "RCB", "LCB")) and not any(k in p_role for k in ("SB", "WB", "RSB", "LSB", "RWB", "LWB"))
                if is_pure_cb:
                    return 0.0

                # 左右の厳格化
                if "RSB" in slot_id or "RWB" in slot_id:
                    if is_left and not is_right:
                        return 0.0  # 右SB/WBに純粋左利きは配置しない
                    if any(k in p_role for k in ("RSB", "RWB")):
                        return 60.0
                elif "LSB" in slot_id or "LWB" in slot_id:
                    if is_left:
                        return 65.0  # 左利き左SB/WBは最優先
                    if any(k in p_role for k in ("LSB", "LWB")):
                        return 60.0

                if any(k in p_role for k in ("SB", "WB", "LSB", "RSB", "LWB", "RWB")):
                    return 50.0
                if any(k in reg for k in ("SB", "WB")):
                    return 45.0
                if any(k in reg for k in ("DF", "MF")) and not is_pure_cb:
                    return 35.0
                return 0.0

        if slot_group == "MF":
            # 純粋CBは中盤に入れない
            if any(k in p_role for k in ("CB", "CCB")) and not any(k in p_role for k in ("DMF", "VO", "CMF")):
                return 0.0

            # ボランチ / アンカー
            if any(k in slot_id for k in ("CH", "DM", "ANCHOR")):
                if any(k in p_role for k in ("DMF", "CMF", "VO", "DM", "CM", "ANCHOR")):
                    return 60.0
                if any(k in reg for k in ("MF", "VO", "DM", "CM")):
                    return 45.0
                return 0.0

            # サイドハーフ / ウイング / シャドー / トップ下
            if any(k in slot_id for k in ("SH", "WG", "ST", "OMF", "RST", "LST")):
                if any(k in p_role for k in ("SMF", "WG", "LWG", "RWG", "OMF", "SH", "ST", "RST", "LST")):
                    return 60.0
                if any(k in reg for k in ("MF", "FW")):
                    return 40.0
                return 0.0

        if slot_group == "FW":
            # CBや守備専任はFWに入れない
            if any(k in p_role for k in ("CB", "CCB", "SB", "WB")):
                return 0.0
            if "DF" in reg:
                return 0.0

            if any(k in slot_id for k in ("CF", "LCF", "RCF")):
                if any(k in p_role for k in ("CF", "ST", "FW")):
                    return 60.0
                if "FW" in reg:
                    return 50.0
                return 0.0

        return 0.0

    # =========================================================================
    # 4. スタメン確率正規化と本命・対抗の判定
    # =========================================================================
    def predict_starting_lineup(
        self,
        team_id: str,
        opponent_team_id: str,
        as_of_date: str,
        formation: Optional[str] = None,
        contender_threshold: float = 0.25,
    ) -> Dict[str, Any]:
        """指定クラブの予想スタメン（本命＋対抗）を決定論算出する."""
        # 1. ホワイトリスト（現所属選手のみ）
        roster = self.get_club_active_roster_whitelist(team_id)
        if not roster:
            raise ValueError(f"No active roster found for team_id: {team_id}")

        # 2. ハード制約除外
        unavailable_ids = self.get_unavailable_player_ids(team_id, opponent_team_id, as_of_date)
        available_roster = [p for p in roster if p["player_id"] not in unavailable_ids]

        # 3. コンテキストデータ取得
        t_prof = self.team_profiles.get(team_id, {})
        opp_prof = self.team_profiles.get(opponent_team_id, {})
        base_f = formation or t_prof.get("base_formation", "4-4-2")
        slots = FORMATION_SLOTS.get(base_f, FORMATION_SLOTS["4-4-2"])

        recent_lineup = self.context_service.get_recent_lineup_and_scorers(team_id, as_of_date)
        fatigue = self.context_service.calculate_schedule_fatigue(team_id, as_of_date)
        player_load = self.context_service.calculate_player_load(team_id, as_of_date)

        # 4. スロット別スコアリング（2パス方式で本命11名とベンチ対抗馬を分離）
        primaries, assigned_player_ids = self._determine_primary_lineup(
            slots=slots,
            available_roster=available_roster,
            recent_lineup=recent_lineup,
            fatigue=fatigue,
            player_load=player_load,
            opp_prof=opp_prof,
        )

        bench_roster = [p for p in available_roster if p["player_id"] not in assigned_player_ids]
        slot_predictions = self._determine_slot_predictions_with_bench_contenders(
            primaries=primaries,
            bench_roster=bench_roster,
            recent_lineup=recent_lineup,
            fatigue=fatigue,
            player_load=player_load,
            opp_prof=opp_prof,
            contender_threshold=contender_threshold,
        )

        # 5. 選手交代想定の生成 (Impact Subs)
        impact_subs = self._simulate_substitution_plan(
            bench_candidates=bench_roster,
            slot_predictions=slot_predictions,
            recent_lineup=recent_lineup,
            fatigue=fatigue,
        )

        return {
            "team_id": team_id,
            "opponent_team_id": opponent_team_id,
            "as_of_date": as_of_date,
            "formation": base_f,
            "unavailable_player_ids": list(unavailable_ids),
            "slots": slot_predictions,
            "impact_subs": impact_subs,
            "display_text": self.format_display_summary(base_f, slot_predictions, impact_subs),
        }

    def _determine_primary_lineup(
        self,
        slots: List[Tuple[str, str, str]],
        available_roster: List[Dict[str, Any]],
        recent_lineup: Dict[str, Any],
        fatigue: Dict[str, Any],
        player_load: Dict[str, Any],
        opp_prof: Dict[str, Any],
    ) -> Tuple[List[Tuple[Tuple[str, str, str], Dict[str, Any], float, List[str]]], Set[str]]:
        """Pass 1: 各スロットに最も適したスタメン11名（Primary）を確定する."""
        assigned_player_ids: Set[str] = set()
        primaries: List[Tuple[Tuple[str, str, str], Dict[str, Any], float, List[str]]] = []

        # GKの決定
        gk_slot = slots[0]
        available_gks = [p for p in available_roster if "GK" in p["position"].upper()]
        gk_scored = []
        for p in available_gks:
            sc, notes = self._calculate_candidate_score(
                player=p,
                slot_id=gk_slot[0],
                slot_group=gk_slot[2],
                recent_lineup=recent_lineup,
                fatigue=fatigue,
                player_load=player_load,
                opp_profile=opp_prof,
            )
            gk_scored.append((p, sc, notes))
        gk_scored.sort(key=lambda x: x[1], reverse=True)
        if gk_scored:
            prim_p, sc, notes = gk_scored[0]
            assigned_player_ids.add(prim_p["player_id"])
            primaries.append((gk_slot, prim_p, sc, notes))

        # フィールドプレイヤーの決定
        field_slots = slots[1:]
        field_roster = [p for p in available_roster if "GK" not in p["position"].upper()]

        for slot in field_slots:
            slot_id, slot_name, slot_group = slot
            candidates = [p for p in field_roster if p["player_id"] not in assigned_player_ids]
            scored = []
            for p in candidates:
                sc, notes = self._calculate_candidate_score(
                    player=p,
                    slot_id=slot_id,
                    slot_group=slot_group,
                    recent_lineup=recent_lineup,
                    fatigue=fatigue,
                    player_load=player_load,
                    opp_profile=opp_prof,
                )
                if sc > 0:
                    scored.append((p, sc, notes))
            scored.sort(key=lambda x: x[1], reverse=True)
            if scored:
                prim_p, sc, notes = scored[0]
                assigned_player_ids.add(prim_p["player_id"])
                primaries.append((slot, prim_p, sc, notes))

        return primaries, assigned_player_ids

    def _determine_slot_predictions_with_bench_contenders(
        self,
        primaries: List[Tuple[Tuple[str, str, str], Dict[str, Any], float, List[str]]],
        bench_roster: List[Dict[str, Any]],
        recent_lineup: Dict[str, Any],
        fatigue: Dict[str, Any],
        player_load: Dict[str, Any],
        opp_prof: Dict[str, Any],
        contender_threshold: float,
    ) -> List[SlotPrediction]:
        """Pass 2: スタメン11名以外のベンチ・控え選手から各スロットの対抗馬（Contender）を選定する."""
        slot_predictions: List[SlotPrediction] = []

        for slot, prim_p, prim_sc, prim_notes in primaries:
            slot_id, slot_name, slot_group = slot

            # このスロットに対するベンチ候補者のスコアを算出
            bench_candidates = [
                p for p in bench_roster
                if (slot_group == "GK" and "GK" in p["position"].upper())
                or (slot_group != "GK" and "GK" not in p["position"].upper())
            ]

            bench_scored = []
            for p in bench_candidates:
                sc, notes = self._calculate_candidate_score(
                    player=p,
                    slot_id=slot_id,
                    slot_group=slot_group,
                    recent_lineup=recent_lineup,
                    fatigue=fatigue,
                    player_load=player_load,
                    opp_profile=opp_prof,
                )
                if sc > 0:
                    bench_scored.append((p, sc, notes))

            bench_scored.sort(key=lambda x: x[1], reverse=True)

            # Primary と ベンチ候補で Softmax 相対確率を計算
            all_pool = [(prim_p, prim_sc, prim_notes)] + bench_scored
            max_sc = max(s[1] for s in all_pool)
            exp_sum = sum(math.exp((s[1] - max_sc) / 15.0) for s in all_pool)

            # Primary Candidate 生成
            prim_prob = math.exp((prim_sc - max_sc) / 15.0) / exp_sum
            primary_candidate = PositionCandidate(
                player_id=prim_p["player_id"],
                player_name=prim_p["canonical_name"],
                number=prim_p["number"],
                registered_pos=prim_p["position"],
                dominant_foot=prim_p["dominant_foot"],
                height_cm=prim_p["height_cm"],
                probability=round(prim_prob, 2),
                score=round(prim_sc, 1),
                notes=prim_notes,
            )

            # Contender Candidate 生成（ベンチ1位が閾値以上か）
            contender_candidate = None
            all_ranked_candidates = [primary_candidate]

            if bench_scored:
                best_bench_p, best_bench_sc, best_bench_notes = bench_scored[0]
                best_bench_prob = math.exp((best_bench_sc - max_sc) / 15.0) / exp_sum
                cont_cand = PositionCandidate(
                    player_id=best_bench_p["player_id"],
                    player_name=best_bench_p["canonical_name"],
                    number=best_bench_p["number"],
                    registered_pos=best_bench_p["position"],
                    dominant_foot=best_bench_p["dominant_foot"],
                    height_cm=best_bench_p["height_cm"],
                    probability=round(best_bench_prob, 2),
                    score=round(best_bench_sc, 1),
                    notes=best_bench_notes,
                )
                all_ranked_candidates.append(cont_cand)
                if best_bench_prob >= contender_threshold:
                    contender_candidate = cont_cand

            slot_predictions.append(
                SlotPrediction(
                    slot_id=slot_id,
                    slot_name=slot_name,
                    primary=primary_candidate,
                    contender=contender_candidate,
                    all_candidates=all_ranked_candidates,
                ),
            )

        return slot_predictions

    def _score_and_rank_candidates(
        self,
        candidates: List[Dict[str, Any]],
        slot_id: str,
        slot_group: str,
        recent_lineup: Dict[str, Any],
        fatigue: Dict[str, Any],
        player_load: Dict[str, Any],
        opp_profile: Dict[str, Any],
        contender_threshold: float,
    ) -> List[PositionCandidate]:
        """候補者リストをスコアリングし、確率でランク付けして返す."""
        scored: List[Tuple[Dict[str, Any], float, List[str]]] = []
        for p in candidates:
            sc, notes = self._calculate_candidate_score(
                player=p,
                slot_id=slot_id,
                slot_group=slot_group,
                recent_lineup=recent_lineup,
                fatigue=fatigue,
                player_load=player_load,
                opp_profile=opp_profile,
            )
            if sc > 0:
                scored.append((p, sc, notes))

        if not scored:
            return []

        # Softmax 風の比率正規化
        max_sc = max(s[1] for s in scored)
        exp_sum = sum(math.exp((s[1] - max_sc) / 15.0) for s in scored)

        results: List[PositionCandidate] = []
        for p, sc, notes in scored:
            prob = math.exp((sc - max_sc) / 15.0) / exp_sum
            results.append(
                PositionCandidate(
                    player_id=p["player_id"],
                    player_name=p["canonical_name"],
                    number=p["number"],
                    registered_pos=p["position"],
                    dominant_foot=p["dominant_foot"],
                    height_cm=p["height_cm"],
                    probability=round(prob, 2),
                    score=round(sc, 1),
                    notes=notes,
                ),
            )

        results.sort(key=lambda x: x.probability, reverse=True)
        return results

    # =========================================================================
    # 5. 交代プラン生成（Impact Subs）
    # =========================================================================
    def _simulate_substitution_plan(
        self,
        bench_candidates: List[Dict[str, Any]],
        slot_predictions: List[SlotPrediction],
        recent_lineup: Dict[str, Any],
        fatigue: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """ベンチ待機濃厚な選手から時間帯別の交代シミュレーションを構築する."""
        bench_map = {p["player_id"]: p for p in bench_candidates}
        plans: List[Dict[str, Any]] = []

        # 実績ある選手を優先するため、total_matches DESC でソート
        experienced_bench = sorted(
            bench_candidates,
            key=lambda x: (x.get("total_matches", 0), x.get("number", 99)),
            reverse=True,
        )

        # 1. 60分前後: 前線・2列目の活性化
        for sp in slot_predictions:
            p = sp.primary
            if "前節早期交代" in p.notes or "連戦高負荷" in p.notes:
                sub_candidates = [
                    bp for bp in experienced_bench
                    if any(k in bp["position"] for k in ("FW", "MF", "WG"))
                    and bp.get("total_matches", 0) > 0
                ]
                if sub_candidates:
                    sub_p = sub_candidates[0]
                    plans.append(
                        {
                            "minute_label": "60分前後",
                            "player_out": p.player_name,
                            "player_in": sub_p["canonical_name"],
                            "position": sp.slot_name,
                            "reason": f"{p.player_name}のコンディション配慮と前線のプレッシング強度維持",
                            "tactical_intent": "前線のギアチェンジ・敵陣での即時奪回ショートカウンター強化",
                        },
                    )
                    experienced_bench.remove(sub_p)
                    break

        # 2. 70分前後: 決定打・勝負ストライカーの投入
        fw_subs = [
            bp for bp in experienced_bench
            if any(k in bp["position"] for k in ("FW", "CF"))
            and bp.get("total_matches", 0) > 0
        ]
        if fw_subs:
            sub_fw = fw_subs[0]
            cf_slots = [sp for sp in slot_predictions if "CF" in sp.slot_id]
            target_sp = cf_slots[0] if cf_slots else slot_predictions[-1]
            plans.append(
                {
                    "minute_label": "70分前後",
                    "player_out": target_sp.primary.player_name,
                    "player_in": sub_fw["canonical_name"],
                    "position": "CF",
                    "reason": "相手守備陣の疲労を突く仕留め役の投入",
                    "tactical_intent": f"{sub_fw['canonical_name']}の走力と決定力を活かした決勝点・追加点の奪取",
                },
            )
            experienced_bench.remove(sub_fw)

        # 3. 75〜80分以降: サイド・中盤のクローズ（守備固め・フレッシュ化）
        df_mf_subs = [
            bp for bp in experienced_bench
            if any(k in bp["position"] for k in ("DF", "SB", "MF", "VO"))
            and bp.get("total_matches", 0) > 0
        ]
        if df_mf_subs:
            sub_def = df_mf_subs[0]
            side_slots = [sp for sp in slot_predictions if any(k in sp.slot_id for k in ("SB", "WB", "SH", "CH"))]
            target_side = side_slots[0] if side_slots else slot_predictions[1]
            plans.append(
                {
                    "minute_label": "75〜80分以降",
                    "player_out": target_side.primary.player_name,
                    "player_in": sub_def["canonical_name"],
                    "position": target_side.slot_name,
                    "reason": "消耗したサイドのインテンシティ回復と守備バランスの維持",
                    "tactical_intent": "被カウンターケアの徹底とゲームクローズ（失点ゼロの完遂）",
                },
            )

        return plans

    # =========================================================================
    # 6. 表示フォーマット生成（本命 ＋ カッコ付き対抗 ＋ 交代想定）
    # =========================================================================
    def format_display_summary(
        self,
        formation: str,
        slots: List[SlotPrediction],
        impact_subs: List[Dict[str, Any]],
    ) -> str:
        """ユーザー指定仕様に基づき、本命＋カッコ付き対抗および交代想定を整形する."""
        lines: List[str] = [f"【予想スタメン：{formation}】"]

        # ポジションカテゴリ別にグループ化
        current_cat = ""
        for sp in slots:
            # カテゴリヘッダー
            cat = "GK" if "GK" in sp.slot_id else ("DF" if any(k in sp.slot_id for k in ("CB", "SB", "WB")) else ("MF" if any(k in sp.slot_id for k in ("CH", "DM", "SH", "OMF", "ANCHOR", "IH", "ST")) else "FW"))
            if cat != current_cat:
                current_cat = cat
                lines.append(f"{cat}:")

            p_txt = f"  ・{sp.slot_name}: {sp.primary.player_name} {int(sp.primary.probability * 100)}%"
            if sp.contender:
                c_notes = f" ※{sp.contender.notes[0]}" if sp.contender.notes else ""
                p_txt += f"（対抗: {sp.contender.player_name} {int(sp.contender.probability * 100)}%{c_notes}）"
            lines.append(p_txt)

        lines.append("")
        lines.append("【想定交代プラン（Impact Subs）】")
        for sub in impact_subs:
            lines.append(
                f"・{sub['minute_label']}: {sub['player_out']} → {sub['player_in']}（{sub['reason']}）",
            )
            lines.append(f"  └ 狙い: {sub['tactical_intent']}")

        return "\n".join(lines)
