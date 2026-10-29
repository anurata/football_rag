"""
Deterministic Tactical Matchup Engine (pipeline/tactical_matchup_engine.py).

Fulfills TACTICAL_PHILOSOPHY_AND_MANIFESTO.md (The 7-Layer Spectrum of Football Truth).
Ingests Layer 1 Ground Truth (physical profile, dominant foot, telemetry, match events)
and Layer 2 Heuristics (team/manager policies, formation dynamics, tradeoffs)
to extract deterministic tactical matchup mismatches across Layer 1 to Layer 6:
1. Aerial Duel Mismatch (Height difference + target reliance)
2. In-Behind vs High Line Mismatch (Top speed / sprints vs defensive line height)
3. Dominant Foot Funneling & Wing Mismatch (Footedness vs press trap / wing dynamics)
4. Formation & System Space Mismatch (Half-space overload & pinning mechanisms)
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
    except Exception as e:
        logger.warning("Failed to read JSON from %s: %s", path, e)
        return default


class TacticalMatchupEngine:
    """
    Deterministic extraction engine for tactical matchup hypotheses (Layer 2 - 6).
    """

    def __init__(
        self,
        db_path: Path = DB_PATH,
        team_profiles_path: Path = TEAM_PROFILES_PATH,
    ) -> None:
        self.db_path = db_path
        self.team_profiles_path = team_profiles_path
        self.team_profiles: Dict[str, Any] = load_json_safely(team_profiles_path, {}).get("teams", {})

    def get_match_players_data(
        self,
        match_id: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Query player_match_stats joined with entity_master_players for a match,
        separated into (home_players, away_players).
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Get home and away team IDs
        cur.execute(
            "SELECT home_team_id, away_team_id FROM matches WHERE match_id = ?",
            (match_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return [], []

        home_team_id = row["home_team_id"]
        away_team_id = row["away_team_id"]

        query = """
            SELECT
                pms.player_id,
                pms.player_name,
                pms.team_id,
                pms.position,
                pms.number,
                pms.is_starter,
                pms.minutes_played,
                pms.distance_km,
                pms.sprints,
                pms.touches,
                pms.goals,
                pms.assists,
                pms.cbp_points,
                pms.raw_stats_json,
                emp.height_cm,
                emp.weight_kg,
                emp.dominant_foot
            FROM player_match_stats pms
            LEFT JOIN entity_master_players emp ON pms.player_id = emp.player_id
            WHERE pms.match_id = ?
        """
        cur.execute(query, (match_id,))
        rows = cur.fetchall()
        conn.close()

        home_players: List[Dict[str, Any]] = []
        away_players: List[Dict[str, Any]] = []

        for r in rows:
            raw_stats = {}
            if r["raw_stats_json"]:
                try:
                    raw_stats = json.loads(r["raw_stats_json"])
                except Exception:
                    pass

            p_dict = {
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
            }

            if r["team_id"] == home_team_id:
                home_players.append(p_dict)
            else:
                away_players.append(p_dict)

        return home_players, away_players

    def extract_aerial_duel_mismatches(
        self,
        attackers: List[Dict[str, Any]],
        defenders: List[Dict[str, Any]],
        att_team_id: str,
        def_team_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract aerial mismatch between tall FW/target man and opponent defenders.
        Trigger: Attacker height >= 185cm or Height Diff >= 7cm against opponent CB/SB.
        """
        mismatches: List[Dict[str, Any]] = []
        att_profile = self.team_profiles.get(att_team_id, {})
        def_profile = self.team_profiles.get(def_team_id, {})

        fw_targets = [
            p for p in attackers
            if (p.get("position") in ["FW", "CF"] or "FW" in str(p.get("position", "")))
            and (p.get("height_cm") or 0) >= 183
        ]

        # Opponent defenders (CB and SB)
        def_line = [
            p for p in defenders
            if p.get("position") in ["DF", "CB", "SB", "WB"]
            or "DF" in str(p.get("position", ""))
        ]

        if not def_line or not fw_targets:
            return mismatches

        for fw in fw_targets:
            fw_height = fw.get("height_cm") or 0
            fw_name = fw.get("player_name", "FW")

            for df in def_line:
                df_height = df.get("height_cm") or 0
                df_name = df.get("player_name", "DF")
                df_pos = df.get("position", "DF")

                # Guard: exclude invalid defender heights (e.g. 0 or None)
                if df_height < 150:
                    continue

                diff = fw_height - df_height

                if diff >= 7:
                    # Aerial mismatch detected
                    pa_entries = fw.get("spaia", {}).get("pa_entries", 0)
                    target_reliance = att_profile.get("in_possession", {}).get("target_reliance", "medium")

                    mismatches.append(
                        {
                            "category": "AERIAL_DUEL_MISMATCH",
                            "attacker": fw_name,
                            "attacker_team": att_team_id,
                            "attacker_height": fw_height,
                            "defender": df_name,
                            "defender_team": def_team_id,
                            "defender_height": df_height,
                            "defender_position": df_pos,
                            "height_diff_cm": diff,
                            "layer1_facts": {
                                "attacker": f"{fw_name} ({fw_height}cm)",
                                "defender": f"{df_name} ({df_height}cm, {df_pos})",
                                "height_advantage_cm": diff,
                                "attacker_pa_entries": pa_entries,
                                "attacker_minutes": fw.get("minutes_played", 0),
                            },
                            "layer2_heuristics": {
                                "concept": "target_man_aerial_superiority",
                                "name": "長身基準点ポスト＆ハイボール標的論",
                                "team_target_reliance": target_reliance,
                            },
                            "layer3_explanation": (
                                f"{fw_name}（{fw_height}cm）が相手{df_pos}の{df_name}（{df_height}cm）に対して"
                                f"+{diff}cmの圧倒的な身長アドバンテージを保持。"
                                f"PA内へのハイボール供給やロングフィードのターゲットとして構造的優位が成立。"
                            ),
                            "layer4_hypothesis": (
                                f"攻撃側は相手CBの迎撃を嫌い、意図的に{df_pos}の{df_name}側へロングボールを落として"
                                f"セカンドボール回収およびPA侵入の足がかりを作った可能性が高い。"
                            ),
                            "layer5_narrative": (
                                f"フィジカルと高さを誇る{fw_name}が相手の防壁に空けた亀裂。"
                                f"高さのミスマッチがピッチ上の均衡を崩す決定打となった。"
                            ),
                            "layer6_forecasting": (
                                f"次節以降、相手守備陣が空中戦対応（競り合いの受け渡しやSBの絞り）を強化しない限り、"
                                f"セットプレーおよびクロスからの失点確率が極めて高くなる。"
                            ),
                        },
                    )

        return mismatches

    def extract_speed_vs_high_line_mismatches(
        self,
        attackers: List[Dict[str, Any]],
        defenders: List[Dict[str, Any]],
        att_team_id: str,
        def_team_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract speed / in-behind threat against high defensive line.
        Trigger: Attacker max_speed >= 33.5 km/h or sprints >= 20 vs defender high line.
        """
        mismatches: List[Dict[str, Any]] = []
        def_profile = self.team_profiles.get(def_team_id, {})
        def_line_type = def_profile.get("out_of_possession", {}).get("defensive_line", "mid_block")

        # Fast runners in attacking team
        sprinters = [
            p for p in attackers
            if (p.get("max_speed_kmh") or 0.0) >= 33.5 or (p.get("sprints") or 0) >= 20
        ]

        if not sprinters:
            return mismatches

        is_high_line = def_line_type in ["high_line", "ultra_high_line", "high_line_extreme"]

        for sp in sprinters:
            p_name = sp.get("player_name", "Sprinter")
            p_pos = sp.get("position", "FW")
            max_spd = sp.get("max_speed_kmh", 0.0)
            sprint_cnt = sp.get("sprints", 0)

            # Check if defender side has slower CBs
            cb_list = [p for p in defenders if p.get("position") in ["DF", "CB"]]
            slowest_cb = None
            if cb_list:
                slowest_cb = min(cb_list, key=lambda p: (p.get("max_speed_kmh") or 35.0))

            cb_name = slowest_cb.get("player_name", "相手CB") if slowest_cb else "相手最終ライン"
            cb_spd = slowest_cb.get("max_speed_kmh") if slowest_cb else None

            speed_diff = (max_spd - cb_spd) if (max_spd and cb_spd) else None

            mismatches.append(
                {
                    "category": "IN_BEHIND_VS_HIGH_LINE",
                    "attacker": p_name,
                    "attacker_team": att_team_id,
                    "attacker_speed": max_spd,
                    "attacker_sprints": sprint_cnt,
                    "defender_team": def_team_id,
                    "defensive_line_type": def_line_type,
                    "target_cb": cb_name,
                    "layer1_facts": {
                        "attacker": f"{p_name} ({p_pos})",
                        "max_speed_kmh": max_spd,
                        "sprints_total": sprint_cnt,
                        "defender_line_policy": def_line_type,
                        "speed_difference_kmh": round(speed_diff, 1) if speed_diff else None,
                    },
                    "layer2_heuristics": {
                        "concept": "high_line_behind_space_exploitation",
                        "name": "ラインブレイカーとハイライン背後広大スペースの力学",
                        "is_high_line_confirmed": is_high_line,
                    },
                    "layer3_explanation": (
                        f"{p_name}のトップスピード{max_spd}km/h（スプリント{sprint_cnt}回）の機動力が、"
                        f"{def_team_id}の{def_line_type}設定によって生じるGK・DFライン間の広大なスペースへ直撃。"
                    ),
                    "layer4_hypothesis": (
                        f"前半から{p_name}を走らせて相手最終ラインを後退（押し下げ）させ、"
                        f"中盤バイタルエリアを空洞化させる戦術的狙いが遂行されていたと推論される。"
                    ),
                    "layer5_narrative": (
                        f"研ぎ澄まされたスプリントが相手の陣形を切り裂き、"
                        f"ハイラインを標榜する相手の生命線に最も痛烈な一撃を見舞った瞬間。"
                    ),
                    "layer6_forecasting": (
                        f"相手側が後半60分以降にDFラインのケア（リトリートまたはスイーパーGKの飛び出し）を怠れば、"
                        f"一瞬のスルーパスから決定的な1対1被弾を招くリスクが極めて高い。"
                    ),
                },
            )

        return mismatches

    def extract_dominant_foot_funneling_mismatches(
        self,
        buildup_players: List[Dict[str, Any]],
        pressing_team_id: str,
        buildup_team_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract dominant foot pressing funnel and side matchup mismatches.
        Trigger: CB / GK footedness imbalance vs opponent pressing funnel policy.
        """
        mismatches: List[Dict[str, Any]] = []
        press_profile = self.team_profiles.get(pressing_team_id, {})
        funnel_policy = press_profile.get("out_of_possession", {}).get("pressing_funnel", "funnel_outside")

        # Focus on build-up line: GK, CBs, and Anchor
        core_buildup = [
            p for p in buildup_players
            if p.get("position") in ["GK", "DF", "CB", "MF", "ボランチ"]
            and p.get("is_starter") == 1
        ]

        if not core_buildup:
            return mismatches

        # Check left foot presence among CBs
        cbs = [p for p in core_buildup if p.get("position") in ["CB", "DF"]]
        left_foot_cbs = [p for p in cbs if p.get("dominant_foot") == "左足"]
        right_foot_cbs = [p for p in cbs if p.get("dominant_foot") == "右足"]

        if cbs and not left_foot_cbs:
            # All CBs are right-footed: potential pressing trigger on left side build-up
            cb_names = ", ".join([p.get("player_name", "") for p in right_foot_cbs[:2]])
            mismatches.append(
                {
                    "category": "DOMINANT_FOOT_FUNNELING",
                    "pressing_team": pressing_team_id,
                    "buildup_team": buildup_team_id,
                    "funnel_policy": funnel_policy,
                    "vulnerability_type": "no_left_footed_cb",
                    "layer1_facts": {
                        "buildup_team": buildup_team_id,
                        "cbs_examined": cb_names,
                        "left_footed_cb_count": 0,
                        "right_footed_cb_count": len(right_foot_cbs),
                        "opponent_pressing_funnel": funnel_policy,
                    },
                    "layer2_heuristics": {
                        "concept": "dominant_foot_funneling_press",
                        "name": "利き足誘導・外切りプレッシングの罠",
                    },
                    "layer3_explanation": (
                        f"{buildup_team_id}の最終ライン（{cb_names}）に純粋な左利きCBが不在。"
                        f"左CBから左サイドへの配球時に右足への持ち替えが発生し、"
                        f"{pressing_team_id}の{funnel_policy}プレスによって外側へハメ込まれやすい構造。"
                    ),
                    "layer4_hypothesis": (
                        f"{pressing_team_id}はスカウティングに基づき、相手の左サイド側ビルドアップを意図的に誘導し、"
                        f"タッチライン際でのボール奪取（ショートカウンター）を狙っていたと考えられる。"
                    ),
                    "layer5_narrative": (
                        f"ピッチ上の幾何学と利き足のコンマ数秒の遅れ。"
                        f"綿密に仕掛けられたプレスの網が、相手のわずかな持ち替えの隙を逃さず捉えた。"
                    ),
                    "layer6_forecasting": (
                        f"次節も左利きCB不在のまま対角線のプレッシャーを受ける場合、"
                        f"自陣深い位置でのロストや苦し紛れのロングクリアからのピンチが再現される可能性が高い。"
                    ),
                },
            )

        return mismatches

    def extract_formation_space_mismatches(
        self,
        home_team_id: str,
        away_team_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract structural spatial advantages from formation matchups (e.g. 4-4-2 vs 3-4-2-1).
        """
        mismatches: List[Dict[str, Any]] = []
        h_profile = self.team_profiles.get(home_team_id, {})
        a_profile = self.team_profiles.get(away_team_id, {})

        h_form = h_profile.get("base_formation", "4-4-2")
        a_form = a_profile.get("base_formation", "4-4-2")

        if "4" in h_form and "3" in a_form:
            # 4-back vs 3-back dynamics
            mismatches.append(
                {
                    "category": "FORMATION_SPACE_MISMATCH",
                    "home_formation": h_form,
                    "away_formation": a_form,
                    "focal_zone": "大外レーンの数的優位 vs ハーフスペースのシャドー浮き",
                    "layer1_facts": {
                        "home_team": home_team_id,
                        "home_formation": h_form,
                        "away_team": away_team_id,
                        "away_formation": a_form,
                    },
                    "layer2_heuristics": {
                        "concept": "four_back_vs_three_back_structural_gap",
                        "name": "4バック vs 3バック システム構造格差",
                    },
                    "layer3_explanation": (
                        f"{home_team_id}（{h_form}）のSH+SB縦2枚に対し、{away_team_id}（{a_form}）はWB1枚。"
                        f"大外レーンで2対1の数的優位を作りやすい反面、"
                        f"自陣2ボランチの脇（ハーフスペース）に相手シャドーが侵入するリスクを内包。"
                    ),
                    "layer4_hypothesis": (
                        f"両指揮官ともに自らの構造的優位ゾーン（サイド突破 vs ライン間攻略）を"
                        f"先に制圧しようとする先制攻撃プランを準備していたと推測される。"
                    ),
                    "layer5_narrative": (
                        f"ピッチの幅と深さを巡るフォーメーションの幾何学バトル。"
                        f"噛み合わない配置同士の隙間を突く頭脳戦が展開された。"
                    ),
                    "layer6_forecasting": (
                        f"サイドで後手に回った側が後半に5バック化またはウイングの位置を下げるシステム変更を"
                        f"余儀なくされるシナリオが予測される。"
                    ),
                },
            )

        return mismatches

    def analyze_match_mismatches(
        self,
        match_id: str,
    ) -> Dict[str, Any]:
        """
        Run full deterministic mismatch extraction for a single match.
        Returns comprehensive structured report conforming to Layer 1 to Layer 6.
        """
        home_players, away_players = self.get_match_players_data(match_id)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT home_team_id, away_team_id, home_score, away_score FROM matches WHERE match_id = ?",
            (match_id,),
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return {
                "match_id": match_id,
                "error": "Match not found in database",
                "mismatches": [],
            }

        h_team, a_team, h_score, a_score = row

        all_mismatches: List[Dict[str, Any]] = []

        # 1. Aerial Mismatches (Both directions)
        aerial_h_vs_a = self.extract_aerial_duel_mismatches(
            attackers=home_players,
            defenders=away_players,
            att_team_id=h_team,
            def_team_id=a_team,
        )
        aerial_a_vs_h = self.extract_aerial_duel_mismatches(
            attackers=away_players,
            defenders=home_players,
            att_team_id=a_team,
            def_team_id=h_team,
        )
        all_mismatches.extend(aerial_h_vs_a)
        all_mismatches.extend(aerial_a_vs_h)

        # 2. Speed vs High Line Mismatches (Both directions)
        speed_h_vs_a = self.extract_speed_vs_high_line_mismatches(
            attackers=home_players,
            defenders=away_players,
            att_team_id=h_team,
            def_team_id=a_team,
        )
        speed_a_vs_h = self.extract_speed_vs_high_line_mismatches(
            attackers=away_players,
            defenders=home_players,
            att_team_id=a_team,
            def_team_id=h_team,
        )
        all_mismatches.extend(speed_h_vs_a)
        all_mismatches.extend(speed_a_vs_h)

        # 3. Dominant Foot Funneling (Both directions)
        foot_h_buildup = self.extract_dominant_foot_funneling_mismatches(
            buildup_players=home_players,
            pressing_team_id=a_team,
            buildup_team_id=h_team,
        )
        foot_a_buildup = self.extract_dominant_foot_funneling_mismatches(
            buildup_players=away_players,
            pressing_team_id=h_team,
            buildup_team_id=a_team,
        )
        all_mismatches.extend(foot_h_buildup)
        all_mismatches.extend(foot_a_buildup)

        # 4. Formation Space Mismatches
        formation_mismatches = self.extract_formation_space_mismatches(
            home_team_id=h_team,
            away_team_id=a_team,
        )
        all_mismatches.extend(formation_mismatches)

        return {
            "match_id": match_id,
            "home_team_id": h_team,
            "away_team_id": a_team,
            "score": f"{h_score}-{a_score}",
            "total_mismatches_found": len(all_mismatches),
            "mismatches": all_mismatches,
        }
