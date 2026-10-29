"""
Deterministic Tactical Matchup Engine (pipeline/tactical_matchup_engine.py).

Fulfills TACTICAL_PHILOSOPHY_AND_MANIFESTO.md (The 7-Layer Spectrum of Football Truth).
Combines multi-source time-series player positions (`player_match_positions` & `match_formations`),
physical/footedness master (`entity_master_players`), and telemetry (`player_match_stats`)
to compute position- and lane-accurate tactical mismatches:
1. Aerial Duel Mismatch (Central CF vs CB / Far-post Isolation vs FB, with time-window overlap)
2. In-Behind vs High Line Mismatch (Sprinters vs strictly CBs, never misclassifying SBs as CBs)
3. Dominant Foot Funneling & Inverted Wing Mismatch (Strictly LCB footedness & Wing vs FB lane matchup)
4. Formation & System Space Mismatch (Actual match formations, in-game shifts, and named key actors)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("tactical_matchup_engine")

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "football.db"
TEAM_PROFILES_PATH = ROOT_DIR / "knowledge" / "team_tactical_profiles.json"


def load_json_safely(path: Path, default: Any = None) -> Any:
    """Load JSON from path safely, returning default on error."""
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to read JSON from %s: %s", path, exc)
        return default


def _normalize_legacy_player(p: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure legacy dict inputs (in unit tests without role_stints) have normalized role/lane/stints."""
    if "role_stints" in p and "primary_role_group" in p:
        return p

    copied = dict(p)
    pos = str(copied.get("position", "")).upper()
    role = str(copied.get("primary_role") or pos or "MF")

    if role in ("RCB", "CCB", "LCB", "CB"):
        rgroup = "CB"
        lane = "LEFT_HALF" if role == "LCB" else ("RIGHT_HALF" if role == "RCB" else "CENTER")
    elif role in ("RSB", "LSB", "SB", "FB"):
        rgroup = "FB"
        lane = "RIGHT" if role == "RSB" else ("LEFT" if role == "LSB" else "RIGHT")
    elif role in ("RWB", "LWB", "WB"):
        rgroup = "WB"
        lane = "RIGHT" if role == "RWB" else "LEFT"
    elif role in ("RWG", "LWG", "RSH", "LSH"):
        rgroup = "WIDE_ATT"
        lane = "RIGHT" if role.startswith("R") else "LEFT"
    elif role in ("OMF", "RST", "LST", "ST"):
        rgroup = "SHADOW"
        lane = "CENTER"
    elif role in ("CF", "RCF", "LCF", "FW"):
        rgroup = "CF"
        lane = "CENTER"
    elif role in ("GK",):
        rgroup = "GK"
        lane = "CENTER"
    elif role in ("DMF", "RDMF", "LDMF", "ボランチ"):
        rgroup = "DMF"
        lane = "CENTER"
    else:
        rgroup = "CMF" if pos == "MF" else ("CB" if pos == "DF" else "CF")
        lane = "CENTER"

    mins = int(copied.get("minutes_played") or 90)
    copied.setdefault("primary_role", role)
    copied.setdefault("primary_role_group", rgroup)
    copied.setdefault("primary_lane", lane)
    copied.setdefault("is_starter", 1)
    copied.setdefault("fluidity_tags", [])
    copied.setdefault("confidence", "HIGH")
    copied.setdefault(
        "role_stints",
        [
            {
                "from_min": 0,
                "to_min": max(15, mins),
                "role": role,
                "role_group": rgroup,
                "lane": lane,
            },
        ],
    )
    return copied


def _are_lanes_opposing(
    att_lane: str,
    att_group: str,
    att_both_flanks: bool,
    def_lane: str,
    def_group: str,
    def_role: str,
) -> Tuple[bool, str]:
    """ピッチ幾何学に基づき、攻撃選手と守備選手が実際に対面しうるレーン関係か判定する."""
    # レガシー単体テストで汎用 'SB'（左右未指定）が渡された場合はファーサイド対面を許容
    if def_role == "SB":
        return (True, "FAR_POST_ISOLATION_VS_FB")

    if att_both_flanks and def_group in ("FB", "WB", "CB"):
        mtype = "CENTRAL_TARGET_VS_CB" if def_group == "CB" else "FLUID_FLANK_ISOLATION_VS_FB"
        return (True, mtype)

    # 中央CF/シャドーは相手CBと主対面、またクロス時のファーサイドでFB/WBとも競り合う
    if att_lane == "CENTER" or att_group == "CF":
        if def_group == "CB":
            return (True, "CENTRAL_TARGET_VS_CB")
        if def_group in ("FB", "WB"):
            return (True, "FAR_POST_ISOLATION_VS_FB")

    # 攻撃側の右レーン(RIGHT/RIGHT_HALF) は 守備側の左レーン(LEFT/LEFT_HALF: LSB, LWB, LCB) と対面
    if att_lane in ("RIGHT", "RIGHT_HALF"):
        if def_lane in ("LEFT", "LEFT_HALF") or def_role == "LCB":
            mtype = "CENTRAL_TARGET_VS_CB" if def_group == "CB" else "DIRECT_LANE_DUEL_VS_FB"
            return (True, mtype)

    # 攻撃側の左レーン(LEFT/LEFT_HALF) は 守備側の右レーン(RIGHT/RIGHT_HALF: RSB, RWB, RCB) と対面
    if att_lane in ("LEFT", "LEFT_HALF"):
        if def_lane in ("RIGHT", "RIGHT_HALF") or def_role == "RCB":
            mtype = "CENTRAL_TARGET_VS_CB" if def_group == "CB" else "DIRECT_LANE_DUEL_VS_FB"
            return (True, mtype)

    return (False, "")


def _find_overlapping_matchup(
    att: Dict[str, Any],
    dfd: Dict[str, Any],
    allowed_att_groups: Set[str],
    allowed_def_groups: Set[str],
    min_overlap_mins: int = 15,
) -> Optional[Dict[str, Any]]:
    """2選手が同一時間帯にピッチ上で対面レーン関係にあった最長区間を返す."""
    att_both = "BOTH_FLANKS" in att.get("fluidity_tags", [])
    best: Optional[Dict[str, Any]] = None

    for sa in att.get("role_stints", []):
        if sa.get("role_group") not in allowed_att_groups:
            continue
        for sd in dfd.get("role_stints", []):
            if sd.get("role_group") not in allowed_def_groups:
                continue
            ov_start = max(int(sa.get("from_min", 0)), int(sd.get("from_min", 0)))
            ov_end = min(int(sa.get("to_min", 90)), int(sd.get("to_min", 90)))
            overlap = ov_end - ov_start
            if overlap < min_overlap_mins:
                continue

            ok, mtype = _are_lanes_opposing(
                att_lane=sa.get("lane", "CENTER"),
                att_group=sa.get("role_group", "CF"),
                att_both_flanks=att_both,
                def_lane=sd.get("lane", "CENTER"),
                def_group=sd.get("role_group", "CB"),
                def_role=sd.get("role", "CB"),
            )
            if not ok:
                continue

            if best is None or overlap > best["overlap_mins"]:
                best = {
                    "from_min": ov_start,
                    "to_min": ov_end,
                    "overlap_mins": overlap,
                    "att_role": sa.get("role", ""),
                    "def_role": sd.get("role", ""),
                    "def_group": sd.get("role_group", ""),
                    "matchup_type": mtype,
                }
    return best


class TacticalMatchupEngine:
    """
    Deterministic extraction engine for position-aware tactical matchup hypotheses (Layer 2 - 6).
    """

    def __init__(
        self,
        db_path: Path = DB_PATH,
        team_profiles_path: Path = TEAM_PROFILES_PATH,
    ) -> None:
        self.db_path = db_path
        self.team_profiles_path = team_profiles_path
        self.team_profiles: Dict[str, Any] = load_json_safely(team_profiles_path, {}).get("teams", {})

    def _table_exists(self, cur: sqlite3.Cursor, table_name: str) -> bool:
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return cur.fetchone() is not None

    def get_match_formations(
        self,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
    ) -> Dict[str, Any]:
        """試合の実フォーメーションおよび試合中システム変更履歴を取得する（未登録時はプロファイルへフォールバック）."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            if self._table_exists(cur, "match_formations"):
                cur.execute(
                    "SELECT * FROM match_formations WHERE match_id = ?",
                    (match_id,),
                )
                row = cur.fetchone()
                if row and (row["home_initial_formation"] or row["away_initial_formation"]):
                    return {
                        "home_formation": row["home_initial_formation"],
                        "away_formation": row["away_initial_formation"],
                        "home_formations": json.loads(row["home_formations_json"] or "[]"),
                        "away_formations": json.loads(row["away_formations_json"] or "[]"),
                        "confidence": row["formation_confidence"],
                        "source": "match_formations_actual",
                    }
        finally:
            conn.close()

        h_prof = self.team_profiles.get(home_team_id, {})
        a_prof = self.team_profiles.get(away_team_id, {})
        hf = h_prof.get("base_formation", "4-4-2")
        af = a_prof.get("base_formation", "4-4-2")
        return {
            "home_formation": hf,
            "away_formation": af,
            "home_formations": [hf],
            "away_formations": [af],
            "confidence": "PROFILE_FALLBACK",
            "source": "team_tactical_profiles",
        }

    def get_match_players_data(
        self,
        match_id: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        player_match_positions を優先軸として entity_master_players および player_match_stats を結合し、
        (home_players, away_players) を返す。未構築試合のみレガシー player_match_stats へフォールバック。
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT home_team_id, away_team_id FROM matches WHERE match_id = ?",
                (match_id,),
            )
            mrow = cur.fetchone()
            if not mrow:
                return ([], [])

            home_team_id = mrow["home_team_id"]
            away_team_id = mrow["away_team_id"]

            if self._table_exists(cur, "player_match_positions"):
                cur.execute(
                    "SELECT COUNT(*) FROM player_match_positions WHERE match_id = ?",
                    (match_id,),
                )
                if cur.fetchone()[0] > 0:
                    return self._query_position_resolved_players(
                        cur,
                        match_id,
                        home_team_id,
                        away_team_id,
                    )

            return self._query_legacy_pms_players(cur, match_id, home_team_id)
        finally:
            conn.close()

    def _query_position_resolved_players(
        self,
        cur: sqlite3.Cursor,
        match_id: str,
        home_team_id: str,
        away_team_id: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """player_match_positions × entity_master_players × player_match_stats を結合取得する."""
        cur.execute(
            """
            SELECT
                pmp.player_id,
                pmp.player_name,
                pmp.team_id,
                pmp.registered_pos,
                pmp.number,
                pmp.is_starter,
                pmp.minutes_estimated,
                pmp.primary_role,
                pmp.primary_role_group,
                pmp.primary_lane,
                pmp.role_stints_json,
                pmp.fluidity_tags_json,
                pmp.confidence,
                emp.height_cm,
                emp.weight_kg,
                emp.dominant_foot,
                pms.minutes_played,
                pms.distance_km,
                pms.sprints,
                pms.touches,
                pms.goals,
                pms.assists,
                pms.cbp_points,
                pms.raw_stats_json
            FROM player_match_positions pmp
            LEFT JOIN entity_master_players emp ON pmp.player_id = emp.player_id
            LEFT JOIN player_match_stats pms
                ON pmp.match_id = pms.match_id AND pmp.player_id = pms.player_id
            WHERE pmp.match_id = ?
            """,
            (match_id,),
        )
        home_players: List[Dict[str, Any]] = []
        away_players: List[Dict[str, Any]] = []

        for r in cur.fetchall():
            raw_stats = json.loads(r["raw_stats_json"]) if r["raw_stats_json"] else {}
            p_dict = {
                "player_id": r["player_id"],
                "player_name": r["player_name"],
                "team_id": r["team_id"],
                "position": r["primary_role"],
                "registered_pos": r["registered_pos"],
                "primary_role": r["primary_role"],
                "primary_role_group": r["primary_role_group"],
                "primary_lane": r["primary_lane"],
                "role_stints": json.loads(r["role_stints_json"] or "[]"),
                "fluidity_tags": json.loads(r["fluidity_tags_json"] or "[]"),
                "confidence": r["confidence"],
                "number": r["number"],
                "is_starter": r["is_starter"],
                "minutes_played": r["minutes_played"] or r["minutes_estimated"],
                "distance_km": r["distance_km"],
                "sprints": r["sprints"],
                "touches": r["touches"],
                "goals": r["goals"],
                "assists": r["assists"],
                "cbp_points": r["cbp_points"],
                "height_cm": r["height_cm"],
                "weight_kg": r["weight_kg"],
                "dominant_foot": r["dominant_foot"],
                "max_speed_kmh": raw_stats.get("max_speed_kmh"),
                "cbp": raw_stats.get("cbp", {}),
                "spaia": raw_stats.get("spaia", {}),
                "raw_stats": raw_stats,
            }
            if r["team_id"] == home_team_id:
                home_players.append(p_dict)
            elif r["team_id"] == away_team_id:
                away_players.append(p_dict)

        return (home_players, away_players)

    def _query_legacy_pms_players(
        self,
        cur: sqlite3.Cursor,
        match_id: str,
        home_team_id: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """player_match_positions 未構築時のレガシー互換取得."""
        cur.execute(
            """
            SELECT
                pms.player_id, pms.player_name, pms.team_id, pms.position,
                pms.number, pms.is_starter, pms.minutes_played, pms.distance_km,
                pms.sprints, pms.touches, pms.goals, pms.assists, pms.cbp_points,
                pms.raw_stats_json, emp.height_cm, emp.weight_kg, emp.dominant_foot
            FROM player_match_stats pms
            LEFT JOIN entity_master_players emp ON pms.player_id = emp.player_id
            WHERE pms.match_id = ? AND (pms.is_starter = 1 OR pms.minutes_played > 0)
            """,
            (match_id,),
        )
        home_players: List[Dict[str, Any]] = []
        away_players: List[Dict[str, Any]] = []
        for r in cur.fetchall():
            raw_stats = json.loads(r["raw_stats_json"]) if r["raw_stats_json"] else {}
            p_dict = _normalize_legacy_player(
                {
                    "player_id": r["player_id"],
                    "player_name": r["player_name"],
                    "team_id": r["team_id"],
                    "position": r["position"],
                    "number": r["number"],
                    "is_starter": r["is_starter"],
                    "minutes_played": r["minutes_played"],
                    "distance_km": r["distance_km"],
                    "sprints": r["sprints"],
                    "touches": r["touches"],
                    "goals": r["goals"],
                    "assists": r["assists"],
                    "cbp_points": r["cbp_points"],
                    "height_cm": r["height_cm"],
                    "weight_kg": r["weight_kg"],
                    "dominant_foot": r["dominant_foot"],
                    "max_speed_kmh": raw_stats.get("max_speed_kmh"),
                    "cbp": raw_stats.get("cbp", {}),
                    "spaia": raw_stats.get("spaia", {}),
                    "raw_stats": raw_stats,
                },
            )
            if r["team_id"] == home_team_id:
                home_players.append(p_dict)
            else:
                away_players.append(p_dict)
        return (home_players, away_players)

    # ------------------------------------------------------------------
    # 1. Aerial Duel Mismatch (同時出場時間帯 × 対面レーン一致のみ)
    # ------------------------------------------------------------------

    def extract_aerial_duel_mismatches(
        self,
        attackers: List[Dict[str, Any]],
        defenders: List[Dict[str, Any]],
        att_team_id: str,
        def_team_id: str,
    ) -> List[Dict[str, Any]]:
        """長身CF/シャドー/WGと、同一時間帯に対面レーンを守るCB/SBとの空中戦ミスマッチを抽出する."""
        mismatches: List[Dict[str, Any]] = []
        att_profile = self.team_profiles.get(att_team_id, {})
        norm_att = [_normalize_legacy_player(p) for p in attackers]
        norm_def = [_normalize_legacy_player(p) for p in defenders]

        att_groups = {"CF", "SHADOW", "WIDE_ATT", "WB"}
        def_groups = {"CB", "FB", "WB"}

        for fw in norm_att:
            fw_height = fw.get("height_cm") or 0
            if fw_height < 180:
                continue
            fw_name = fw.get("player_name", "FW")
            is_fluid = "BOTH_FLANKS" in fw.get("fluidity_tags", []) or "ROLE_SHIFTED" in fw.get("fluidity_tags", [])

            for df in norm_def:
                df_height = df.get("height_cm") or 0
                if df_height < 150:
                    continue
                diff = fw_height - df_height
                if diff < 7:
                    continue

                ov = _find_overlapping_matchup(fw, df, att_groups, def_groups)
                if not ov:
                    continue
                # 中央CB相手なら183cm以上を要求、小柄SB相手なら180cm以上でも+8cm以上で成立
                if ov["def_group"] == "CB" and fw_height < 183:
                    continue
                if ov["def_group"] != "CB" and fw_height < 183 and diff < 8:
                    continue

                df_name = df.get("player_name", "DF")
                att_role = ov["att_role"]
                def_role = ov["def_role"]
                window_str = f"{ov['from_min']}〜{ov['to_min']}分"
                fluid_note = (
                    "（※試合中にポジション・左右レーンを可変移動するため、狙い所を選択可能）"
                    if is_fluid or "ROLE_SHIFTED" in df.get("fluidity_tags", [])
                    else ""
                )
                pa_entries = fw.get("spaia", {}).get("pa_entries", 0)
                target_reliance = att_profile.get("in_possession", {}).get("target_reliance", "medium")

                mismatches.append(
                    {
                        "category": "AERIAL_DUEL_MISMATCH",
                        "matchup_type": ov["matchup_type"],
                        "time_window": window_str,
                        "attacker": fw_name,
                        "attacker_role": att_role,
                        "attacker_team": att_team_id,
                        "attacker_height": fw_height,
                        "defender": df_name,
                        "defender_team": def_team_id,
                        "defender_height": df_height,
                        "defender_position": def_role,
                        "height_diff_cm": diff,
                        "position_confidence": df.get("confidence", "HIGH"),
                        "layer1_facts": {
                            "attacker": f"{fw_name} ({fw_height}cm, {att_role})",
                            "defender": f"{df_name} ({df_height}cm, {def_role})",
                            "active_overlap_window": window_str,
                            "height_advantage_cm": diff,
                            "attacker_pa_entries": pa_entries,
                            "attacker_minutes": fw.get("minutes_played", 0),
                        },
                        "layer2_heuristics": {
                            "concept": "target_man_aerial_superiority",
                            "name": "対面レーン別ハイボール標的＆ファーサイドアイソレーション論",
                            "team_target_reliance": target_reliance,
                        },
                        "layer3_explanation": (
                            f"[{window_str}] {att_role}の{fw_name}（{fw_height}cm）が対面・競り合い圏内の"
                            f"{def_role} {df_name}（{df_height}cm）に対して+{diff}cmの身長優位を保持。{fluid_note}"
                        ),
                        "layer4_hypothesis": (
                            f"攻撃側は中央CBとの正面衝突を避け、{def_role}（{df_name}）の大外・ファーサイドへ"
                            f"斜めのハイボールを供給する設計だった可能性が高い。"
                            if ov["def_group"] != "CB"
                            else f"攻撃側は{def_role}（{df_name}）との競り合いに基準点（{fw_name}）を当て、"
                            f"セカンドボール回収から敵陣進入を図る狙いを持っていたと推論される。"
                        ),
                        "layer5_narrative": (
                            f"ピッチ上の配置が噛み合った{window_str}、{fw_name}の高さが{def_team_id}守備網に空けた構造的亀裂。"
                        ),
                        "layer6_forecasting": (
                            f"相手守備陣が{def_role}側への絞りとカバーリングを徹底しない限り、"
                            f"クロスおよびセットプレーからの失点リスクが高止まりする。"
                        ),
                    },
                )

        mismatches.sort(key=lambda m: m["height_diff_cm"], reverse=True)
        return mismatches

    # ------------------------------------------------------------------
    # 2. In-Behind vs High Line Mismatch (守備比較対象を純粋なCBのみに限定)
    # ------------------------------------------------------------------

    def extract_speed_vs_high_line_mismatches(
        self,
        attackers: List[Dict[str, Any]],
        defenders: List[Dict[str, Any]],
        att_team_id: str,
        def_team_id: str,
    ) -> List[Dict[str, Any]]:
        """俊足アタッカーと相手CB陣（SBを除外した純粋なCBのみ）の背後スペースミスマッチを抽出する."""
        mismatches: List[Dict[str, Any]] = []
        def_profile = self.team_profiles.get(def_team_id, {})
        def_line_type = def_profile.get("out_of_possession", {}).get("defensive_line", "mid_block")

        norm_att = [_normalize_legacy_player(p) for p in attackers]
        norm_def = [_normalize_legacy_player(p) for p in defenders]

        sprinters = [
            p for p in norm_att
            if p.get("primary_role_group") in {"CF", "WIDE_ATT", "SHADOW", "WB", "FB"}
            and ((p.get("max_speed_kmh") or 0.0) >= 33.5 or (p.get("sprints") or 0) >= 20)
        ]
        if not sprinters:
            return mismatches

        is_high_line = def_line_type in ["high_line", "ultra_high_line", "high_line_extreme"]
        # 厳密に role_group == "CB" の選手のみから比較（SBを誤抽出しない）
        pure_cbs = [p for p in norm_def if p.get("primary_role_group") == "CB" and p.get("is_starter") == 1]
        if not pure_cbs:
            pure_cbs = [p for p in norm_def if p.get("primary_role_group") == "CB"]

        slowest_cb = (
            min(pure_cbs, key=lambda p: (p.get("max_speed_kmh") or 35.0))
            if pure_cbs
            else None
        )
        cb_name = slowest_cb.get("player_name", "相手CB") if slowest_cb else "相手CBライン"
        cb_role = slowest_cb.get("primary_role", "CB") if slowest_cb else "CB"
        cb_spd = slowest_cb.get("max_speed_kmh") if slowest_cb else None

        for sp in sprinters:
            p_name = sp.get("player_name", "Sprinter")
            p_role = sp.get("primary_role", "FW")
            max_spd = sp.get("max_speed_kmh", 0.0)
            sprint_cnt = sp.get("sprints", 0)
            speed_diff = (max_spd - cb_spd) if (max_spd and cb_spd) else None

            mismatches.append(
                {
                    "category": "IN_BEHIND_VS_HIGH_LINE",
                    "attacker": p_name,
                    "attacker_role": p_role,
                    "attacker_team": att_team_id,
                    "attacker_speed": max_spd,
                    "attacker_sprints": sprint_cnt,
                    "defender_team": def_team_id,
                    "defensive_line_type": def_line_type,
                    "target_cb": f"{cb_name} ({cb_role})",
                    "layer1_facts": {
                        "attacker": f"{p_name} ({p_role})",
                        "max_speed_kmh": max_spd,
                        "sprints_total": sprint_cnt,
                        "defender_line_policy": def_line_type,
                        "target_cb": f"{cb_name} ({cb_role})",
                        "speed_difference_kmh": round(speed_diff, 1) if speed_diff else None,
                    },
                    "layer2_heuristics": {
                        "concept": "high_line_behind_space_exploitation",
                        "name": "ラインブレイカーとハイライン背後スペースの力学",
                        "is_high_line_confirmed": is_high_line,
                    },
                    "layer3_explanation": (
                        f"{p_role}の{p_name}（最高速{max_spd}km/h・スプリント{sprint_cnt}回）が、"
                        f"{def_team_id}の{def_line_type}（{cb_role}: {cb_name}）背後のスペースへ直撃。"
                    ),
                    "layer4_hypothesis": (
                        f"{p_name}の背後ランニングで相手CB陣をピン留めして最終ラインを押し下げ、"
                        f"中盤ライン間のスペースを広げる狙いが組み込まれていたと推論される。"
                    ),
                    "layer5_narrative": (
                        f"研ぎ澄まされたスプリントが{def_team_id}の最終ライン裏を突き続けたスピードの駆け引き。"
                    ),
                    "layer6_forecasting": (
                        f"後半60分以降に相手の中盤プレス強度が落ちた瞬間、{p_name}へのスルーパスから"
                        f"決定機が生まれる確率が一段と高まる。"
                    ),
                },
            )
        return mismatches

    # ------------------------------------------------------------------
    # 3. Dominant Foot Funneling & Inverted Wing Mismatch (純粋なCB・対面SB限定)
    # ------------------------------------------------------------------

    def extract_dominant_foot_funneling_mismatches(
        self,
        buildup_players: List[Dict[str, Any]],
        pressing_team_id: str,
        buildup_team_id: str,
        pressing_players: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        厳密に先発CB（RCB/CCB/LCB）のみを対象に左CB右足配置・左利きCB不在の誘導脆弱性を検出し、
        左SBの左利き選手をCBと誤認するバグを防ぐ。
        """
        mismatches: List[Dict[str, Any]] = []
        press_profile = self.team_profiles.get(pressing_team_id, {})
        funnel_policy = press_profile.get("out_of_possession", {}).get("pressing_funnel", "funnel_outside")

        norm_buildup = [_normalize_legacy_player(p) for p in buildup_players]
        # 重要: DF全体ではなく role_group == "CB" の先発選手のみ抽出（左利きLSBによる誤判定を完全防止）
        starter_cbs = [
            p for p in norm_buildup
            if p.get("primary_role_group") == "CB" and p.get("is_starter") == 1
        ]
        if not starter_cbs:
            return mismatches

        left_foot_cbs = [p for p in starter_cbs if p.get("dominant_foot") == "左足"]
        right_foot_cbs = [p for p in starter_cbs if p.get("dominant_foot") == "右足"]
        lcb_players = [p for p in starter_cbs if p.get("primary_role") == "LCB"]
        right_footed_lcb = [p for p in lcb_players if p.get("dominant_foot") == "右足"]

        if (right_footed_lcb or not left_foot_cbs) and right_foot_cbs:
            vuln_type = "right_footed_lcb" if right_footed_lcb else "no_left_footed_cb"
            target_names = (
                ", ".join(f"{p['player_name']}({p['primary_role']})" for p in right_footed_lcb)
                if right_footed_lcb
                else ", ".join(f"{p['player_name']}({p['primary_role']})" for p in right_foot_cbs[:3])
            )
            mismatches.append(
                {
                    "category": "DOMINANT_FOOT_FUNNELING",
                    "pressing_team": pressing_team_id,
                    "buildup_team": buildup_team_id,
                    "funnel_policy": funnel_policy,
                    "vulnerability_type": (
                        "no_left_footed_cb" if not left_foot_cbs else vuln_type
                    ),
                    "layer1_facts": {
                        "buildup_team": buildup_team_id,
                        "cbs_examined": ", ".join(
                            f"{p.get('player_name', '')}({p.get('primary_role', 'CB')}:{p.get('dominant_foot', '不明')})"
                            for p in starter_cbs
                        ),
                        "left_footed_cb_count": len(left_foot_cbs),
                        "right_footed_cb_count": len(right_foot_cbs),
                        "right_footed_lcb": target_names,
                        "opponent_pressing_funnel": funnel_policy,
                    },
                    "layer2_heuristics": {
                        "concept": "dominant_foot_funneling_press",
                        "name": "左CB右足配置に対する利き足誘導・外切りプレッシングの罠",
                    },
                    "layer3_explanation": (
                        f"{buildup_team_id}の先発CB陣において左CB（{target_names}）が右利き。"
                        f"左サイドへの配球や内向きトラップ時に持ち替え角度の制約が生じ、"
                        f"{pressing_team_id}の{funnel_policy}プレスに狙われやすい構造。"
                    ),
                    "layer4_hypothesis": (
                        f"{pressing_team_id}は相手右CB側を切りながら左CB（{target_names}）へ誘導し、"
                        f"左タッチライン際での圧縮奪取を狙うプレス設計が可能。"
                    ),
                    "layer5_narrative": (
                        f"最終ラインの利き足と身体の向きを巡るコンマ数秒の駆け引き。"
                    ),
                    "layer6_forecasting": (
                        f"左CB脇へのボランチ降りやGKを使ったプレス回避を用意しない場合、"
                        f"左サイド低い位置でのロストからショートカウンターを浴びるリスクが高い。"
                    ),
                },
            )

        return mismatches

    # ------------------------------------------------------------------
    # 4. Formation & System Space Mismatch (実試合フォーメーション＆配置選手名を使用)
    # ------------------------------------------------------------------

    def extract_formation_space_mismatches(
        self,
        home_team_id: str,
        away_team_id: str,
        home_formation: Optional[str] = None,
        away_formation: Optional[str] = None,
        home_players: Optional[List[Dict[str, Any]]] = None,
        away_players: Optional[List[Dict[str, Any]]] = None,
        home_formations_history: Optional[List[str]] = None,
        away_formations_history: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """実試合フォーメーション（および試合中の可変推移）からシステム噛み合わせの空間ギャップを抽出する."""
        mismatches: List[Dict[str, Any]] = []
        h_profile = self.team_profiles.get(home_team_id, {})
        a_profile = self.team_profiles.get(away_team_id, {})

        h_form = home_formation or h_profile.get("base_formation", "4-4-2")
        a_form = away_formation or a_profile.get("base_formation", "4-4-2")
        h_hist = home_formations_history or [h_form]
        a_hist = away_formations_history or [a_form]

        h_is_4 = h_form.startswith("4")
        a_is_3 = a_form.startswith("3") or a_form.startswith("5")
        h_is_3 = h_form.startswith("3") or h_form.startswith("5")
        a_is_4 = a_form.startswith("4")

        if (h_is_4 and a_is_3) or (h_is_3 and a_is_4):
            four_team = home_team_id if h_is_4 else away_team_id
            four_form = h_form if h_is_4 else a_form
            four_plist = home_players if h_is_4 else away_players

            three_team = away_team_id if h_is_4 else home_team_id
            three_form = a_form if h_is_4 else h_form
            three_plist = away_players if h_is_4 else home_players

            wide_names = self._pick_role_names(four_plist, {"FB", "WIDE_ATT"})
            shadow_names = self._pick_role_names(three_plist, {"SHADOW", "WB"})
            shift_note = ""
            if len(h_hist) > 1 or len(a_hist) > 1:
                shift_note = f"（※試合中システム推移: {home_team_id}={'→'.join(h_hist)}, {away_team_id}={'→'.join(a_hist)}）"

            mismatches.append(
                {
                    "category": "FORMATION_SPACE_MISMATCH",
                    "home_formation": h_form,
                    "away_formation": a_form,
                    "home_formations_history": h_hist,
                    "away_formations_history": a_hist,
                    "focal_zone": "大外レーンの2対1数的優位 vs 脇ハーフスペースのシャドー浮き",
                    "layer1_facts": {
                        "home_team": home_team_id,
                        "home_formation": h_form,
                        "home_formations_history": h_hist,
                        "away_team": away_team_id,
                        "away_formation": a_form,
                        "away_formations_history": a_hist,
                    },
                    "layer2_heuristics": {
                        "concept": "four_back_vs_three_back_structural_gap",
                        "name": "4バック vs 3バック システム構造格差",
                    },
                    "layer3_explanation": (
                        f"{four_team}（{four_form}）のサイド縦2枚{wide_names}に対し、"
                        f"{three_team}（{three_form}）はWB1枚対応となり大外で2対1が生じやすい一方、"
                        f"{three_team}のシャドー／WB{shadow_names}がボランチ脇ハーフスペースを突きやすい噛み合わせ。{shift_note}"
                    ),
                    "layer4_hypothesis": (
                        f"{four_team}は大外からのサイド攻略、{three_team}は5レーンを埋めたハーフスペース侵入で"
                        f"先に相手WB／SBをピン留めしようと意図していたと推測される。"
                    ),
                    "layer5_narrative": (
                        f"{h_form}対{a_form}、噛み合わない配置のズレをどちらが自軍の土俵に引きずり込むかの構造戦。"
                    ),
                    "layer6_forecasting": (
                        f"サイドで押し込まれた側が後半にウイングを最終ラインへ落とす5バック化、または"
                        f"システム変更に踏み切る展開が予測される。"
                    ),
                },
            )
        return mismatches

    def _pick_role_names(
        self,
        players: Optional[List[Dict[str, Any]]],
        groups: Set[str],
    ) -> str:
        """指定ロールグループの先発選手名を最大2名括弧付き文字列で返す."""
        if not players:
            return ""
        names = [
            p.get("player_name", "")
            for p in players
            if p.get("is_starter") == 1 and p.get("primary_role_group") in groups and p.get("player_name")
        ]
        return f"（{', '.join(names[:2])}ら）" if names else ""

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------

    def analyze_match_mismatches(
        self,
        match_id: str,
    ) -> Dict[str, Any]:
        """単一試合のポジション・レーン・時間帯厳密化済み4大ミスマッチを一括抽出する."""
        home_players, away_players = self.get_match_players_data(match_id)

        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT home_team_id, away_team_id, home_score, away_score FROM matches WHERE match_id = ?",
                (match_id,),
            )
            row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            return {
                "match_id": match_id,
                "error": "Match not found in database",
                "mismatches": [],
            }

        h_team, a_team, h_score, a_score = row
        form_info = self.get_match_formations(match_id, h_team, a_team)

        all_mismatches: List[Dict[str, Any]] = []

        # 1. Aerial Mismatches
        all_mismatches.extend(
            self.extract_aerial_duel_mismatches(home_players, away_players, h_team, a_team),
        )
        all_mismatches.extend(
            self.extract_aerial_duel_mismatches(away_players, home_players, a_team, h_team),
        )

        # 2. Speed vs High Line Mismatches
        all_mismatches.extend(
            self.extract_speed_vs_high_line_mismatches(home_players, away_players, h_team, a_team),
        )
        all_mismatches.extend(
            self.extract_speed_vs_high_line_mismatches(away_players, home_players, a_team, h_team),
        )

        # 3. Dominant Foot Funneling
        all_mismatches.extend(
            self.extract_dominant_foot_funneling_mismatches(home_players, a_team, h_team, away_players),
        )
        all_mismatches.extend(
            self.extract_dominant_foot_funneling_mismatches(away_players, h_team, a_team, home_players),
        )

        # 4. Formation Space Mismatches
        all_mismatches.extend(
            self.extract_formation_space_mismatches(
                home_team_id=h_team,
                away_team_id=a_team,
                home_formation=form_info["home_formation"],
                away_formation=form_info["away_formation"],
                home_players=home_players,
                away_players=away_players,
                home_formations_history=form_info["home_formations"],
                away_formations_history=form_info["away_formations"],
            ),
        )

        return {
            "match_id": match_id,
            "home_team_id": h_team,
            "away_team_id": a_team,
            "home_formation": form_info["home_formation"],
            "away_formation": form_info["away_formation"],
            "formation_source": form_info["source"],
            "score": f"{h_score}-{a_score}",
            "total_mismatches_found": len(all_mismatches),
            "mismatches": all_mismatches,
        }
