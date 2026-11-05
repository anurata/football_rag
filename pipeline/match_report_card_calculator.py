# -*- coding: utf-8 -*-
"""
Match Report Card Calculator (pipeline/match_report_card_calculator.py).
Calculates the 6-dimension report card (Game Dominance, Individual Power,
Style Execution, Duels & Intensity, Team Cohesion, Excitement Index)
conforming to docs/MATCH_REPORT_CARD_SPECIFICATION.md and El Golasso's
reporter scorecard standard.
Implements outcome decay factor (gamma) and negative excitement penalties
so that the sum of the 6 metrics always perfectly equals the total score.
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection


class MatchReportCardCalculator:
    """Calculates 6-metric scorecard and overall grade (S to D) for any match and team."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        archetypes_path: Optional[str] = None,
        derbies_path: Optional[str] = None,
    ) -> None:
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        self.archetypes_path = Path(
            archetypes_path or (ROOT_DIR / "config" / "team_style_archetypes.json"),
        )
        self.derbies_path = Path(
            derbies_path or (ROOT_DIR / "config" / "derby_matches.json"),
        )
        self.archetypes: Dict[str, Any] = self._load_json(self.archetypes_path)
        self.derbies: List[Dict[str, Any]] = self._load_json(self.derbies_path).get(
            "derbies",
            [],
        )

    def _load_json(self, path: Path) -> Any:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def is_derby_match(self, team_a: str, team_b: str) -> Optional[str]:
        """Check if matchup is a recognized derby match."""
        pair = {team_a, team_b}
        for d in self.derbies:
            if set(d.get("teams", [])) == pair:
                return d.get("name", "ダービーマッチ")
        return None

    def compute_outcome_decay_factor(
        self,
        team_score: int,
        opp_score: int,
    ) -> float:
        """Calculate outcome decay factor gamma based on win/draw/loss and goal difference."""
        diff = team_score - opp_score
        if diff > 0:
            if diff >= 3:
                return 1.10
            elif diff >= 2:
                return 1.05
            else:
                return 1.00
        elif diff == 0:
            return 0.90
        else:
            if diff <= -3:
                return 0.65
            elif diff == -2:
                return 0.72
            else:
                return 0.80

    def calculate_report_card(
        self,
        match_id: str,
        team_id: str,
    ) -> Dict[str, Any]:
        """Calculate complete 6-metric report card for target team in specified match."""
        conn = get_db_connection(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # 1. Fetch match metadata
            cur.execute(
                "SELECT * FROM matches WHERE match_id = ?",
                (match_id,),
            )
            m = cur.fetchone()
            if not m:
                raise ValueError(f"Match not found: {match_id}")

            is_home = m["home_team_id"] == team_id
            opp_id = m["away_team_id"] if is_home else m["home_team_id"]
            team_score = m["home_score"] if is_home else m["away_score"]
            opp_score = m["away_score"] if is_home else m["home_score"]

            # 2. Fetch team FLAB stats
            cur.execute(
                "SELECT * FROM team_match_flab_stats WHERE match_id = ? AND team_id = ?",
                (match_id, team_id),
            )
            t_flab_row = cur.fetchone()
            t_flab = dict(t_flab_row) if t_flab_row else {}

            cur.execute(
                "SELECT * FROM team_match_flab_stats WHERE match_id = ? AND team_id = ?",
                (match_id, opp_id),
            )
            o_flab_row = cur.fetchone()
            o_flab = dict(o_flab_row) if o_flab_row else {}

            # 3. Fetch player stats
            cur.execute(
                """
                SELECT * FROM player_match_stats
                WHERE match_id = ? AND team_id = ?
                """,
                (match_id, team_id),
            )
            players = [dict(row) for row in cur.fetchall()]

            # 4. Fetch match events
            cur.execute(
                """
                SELECT * FROM match_events
                WHERE match_id = ?
                ORDER BY minute ASC
                """,
                (match_id,),
            )
            events = [dict(row) for row in cur.fetchall()]

            # 5. Fetch all teams' stats for the same matchweek to compute percentiles
            matchweek = m["matchweek"]
            cur.execute(
                """
                SELECT f.* FROM team_match_flab_stats f
                JOIN matches m ON f.match_id = m.match_id
                WHERE m.matchweek = ?
                """,
                (matchweek,),
            )
            mw_stats = [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

        # 6. Compute Raw Scores for 6 Dimensions
        raw_1, details_1 = self._calc_game_dominance(
            t_flab=t_flab,
            o_flab=o_flab,
            team_score=team_score,
            opp_score=opp_score,
        )
        raw_2, details_2 = self._calc_individual_power(
            t_flab=t_flab,
            players=players,
            team_score=team_score,
            opp_score=opp_score,
        )
        raw_3, details_3 = self._calc_style_execution(
            team_id=team_id,
            t_flab=t_flab,
            mw_stats=mw_stats,
            team_score=team_score,
            opp_score=opp_score,
        )
        raw_4, details_4 = self._calc_duels_intensity(
            t_flab=t_flab,
            players=players,
            team_score=team_score,
            opp_score=opp_score,
        )
        raw_5, details_5 = self._calc_team_cohesion(
            t_flab=t_flab,
            players=players,
            team_score=team_score,
            opp_score=opp_score,
        )
        raw_6, details_6 = self._calc_excitement_index(
            team_id=team_id,
            opp_id=opp_id,
            team_score=team_score,
            opp_score=opp_score,
            events=events,
            t_flab=t_flab,
            o_flab=o_flab,
            is_home=is_home,
        )

        # 7. Apply Outcome Decay Factor (gamma) across all dimensions
        gamma = self.compute_outcome_decay_factor(team_score, opp_score)

        score_1 = max(0, min(10, round(raw_1 * gamma)))
        score_2 = max(0, min(10, round(raw_2 * gamma)))
        score_3 = max(0, min(10, round(raw_3 * gamma)))
        score_4 = max(0, min(10, round(raw_4 * gamma)))
        score_5 = max(0, min(10, round(raw_5 * gamma)))
        score_6 = max(0, min(10, round(raw_6 * gamma)))

        # Update details with decay info
        for d, r in [(details_1, raw_1), (details_2, raw_2), (details_3, raw_3),
                    (details_4, raw_4), (details_5, raw_5), (details_6, raw_6)]:
            d["raw_unscaled"] = r
            d["gamma"] = gamma

        # 8. Total Score is exactly the sum of the 6 calibrated metric scores
        total_score = score_1 + score_2 + score_3 + score_4 + score_5 + score_6
        rank = self._determine_rank(total_score)

        result = {
            "match_id": match_id,
            "team_id": team_id,
            "opp_team_id": opp_id,
            "is_home": is_home,
            "score": f"{team_score}-{opp_score}",
            "total_score": total_score,
            "rank": rank,
            "decay_factor": gamma,
            "metrics": {
                "game_dominance": {
                    "name": "①ゲーム支配",
                    "score": score_1,
                    "details": details_1,
                },
                "individual_power": {
                    "name": "②個人パワー",
                    "score": score_2,
                    "details": details_2,
                },
                "style_execution": {
                    "name": "③スタイル発揮",
                    "score": score_3,
                    "details": details_3,
                },
                "duels_intensity": {
                    "name": "④球際",
                    "score": score_4,
                    "details": details_4,
                },
                "team_cohesion": {
                    "name": "⑤リレーション",
                    "score": score_5,
                    "details": details_5,
                },
                "excitement_index": {
                    "name": "⑥興奮度",
                    "score": score_6,
                    "details": details_6,
                },
            },
        }

        # 9. Generate El Golasso style critique
        result["critique"] = self.generate_critique(result)
        return result

    # -------------------------------------------------------------------------
    # Dimension Calculators
    # -------------------------------------------------------------------------

    def _calc_game_dominance(
        self,
        t_flab: Dict[str, Any],
        o_flab: Dict[str, Any],
        team_score: int,
        opp_score: int,
    ) -> Tuple[float, Dict[str, Any]]:
        """1. Game Dominance (Raw Base)"""
        poss = float(t_flab.get("possession_rate") or 50.0)
        t_m30 = float(t_flab.get("m30_entries") or 0.0)
        o_m30 = float(o_flab.get("m30_entries") or 0.0)
        field_tilt = (t_m30 / max(t_m30 + o_m30, 1.0)) * 100.0

        t_xg = float(t_flab.get("xg") or 0.0)
        o_xg = float(o_flab.get("xg") or 0.0)
        xg_diff = t_xg - o_xg

        s_poss = (poss - 50.0) * 0.06
        s_tilt = (field_tilt - 50.0) * 0.04
        s_suppress = xg_diff * 0.6

        raw = 5.0 + s_poss + s_tilt + s_suppress
        if opp_score == 0 and team_score > 0:
            raw += 0.5  # Clean sheet bonus

        return raw, {
            "possession_rate": poss,
            "field_tilt": round(field_tilt, 1),
            "xg_diff": round(xg_diff, 2),
            "raw_score": round(raw, 2),
        }

    def _calc_individual_power(
        self,
        t_flab: Dict[str, Any],
        players: List[Dict[str, Any]],
        team_score: int,
        opp_score: int,
    ) -> Tuple[float, Dict[str, Any]]:
        """2. Individual Power (Raw Base)"""
        dribbles = float(t_flab.get("dribbles") or 0.0)
        drib_rate = float(t_flab.get("dribbles_rate") or 0.0)
        drib_succ = dribbles * (drib_rate / 100.0)

        ratings = []
        max_goals = 0
        for p in players:
            g = int(p.get("goals") or 0)
            if g > max_goals:
                max_goals = g
            raw_str = p.get("raw_stats_json")
            if raw_str:
                try:
                    p_raw = json.loads(raw_str)
                    r = float(p_raw.get("rating") or 6.0)
                    ratings.append(r)
                except Exception:
                    pass
        max_rating = max(ratings) if ratings else 6.0

        t_m30 = float(t_flab.get("m30_entries") or 0.0)
        t_crosses = float(t_flab.get("crosses") or 0.0)
        non_shot_obv = t_m30 * 0.02 + t_crosses * 0.015 + drib_succ * 0.025

        bench = [p for p in players if not p.get("is_starter") and (p.get("minutes_played") or 0) > 0]
        sub_mva = sum(float(p.get("xg") or 0.0) + float(p.get("xa") or 0.0) for p in bench)

        s_drib = (drib_succ - 6.0) * 0.15
        s_rating = (max_rating - 6.0) * 1.0
        s_threat = (non_shot_obv - 1.5) * 0.25
        s_sub = min(sub_mva * 0.8, 1.0)
        s_brace = 1.0 if max_goals >= 2 else (0.5 if max_goals == 1 else 0.0)

        raw = 5.0 + s_drib + s_rating + s_threat + s_sub + s_brace

        return raw, {
            "dribble_success": round(drib_succ, 1),
            "max_player_rating": max_rating,
            "max_single_goals": max_goals,
            "non_shot_obv": round(non_shot_obv, 2),
            "sub_mva": round(sub_mva, 2),
            "raw_score": round(raw, 2),
        }

    def _calc_style_execution(
        self,
        team_id: str,
        t_flab: Dict[str, Any],
        mw_stats: List[Dict[str, Any]],
        team_score: int,
        opp_score: int,
    ) -> Tuple[float, Dict[str, Any]]:
        """3. Tactical Style Execution (Raw Base)"""
        arch = self.archetypes.get(team_id, {})
        key_metrics = arch.get(
            "key_metrics",
            ["cbp_attack", "sprints", "chance_create_rate", "pa_entries"],
        )
        directions = arch.get("direction", {})

        percentiles = []
        growth_ratios = []

        for m_key in key_metrics:
            is_high = directions.get(m_key, "high") == "high"
            match_val = float(t_flab.get(m_key) or 0.0)
            avg_val = float(t_flab.get(f"{m_key}_avg") or match_val)

            all_vals = [float(st.get(m_key) or 0.0) for st in mw_stats if m_key in st]
            if len(all_vals) > 1:
                if is_high:
                    rank_pct = sum(1 for v in all_vals if match_val >= v) / float(len(all_vals))
                else:
                    rank_pct = sum(1 for v in all_vals if match_val <= v) / float(len(all_vals))
            else:
                rank_pct = 0.5
            percentiles.append(rank_pct)

            if avg_val > 0:
                growth_ratios.append(match_val / avg_val)

        avg_pct = sum(percentiles) / max(len(percentiles), 1)
        base_score = avg_pct * 10.0

        avg_growth = sum(growth_ratios) / max(len(growth_ratios), 1) if growth_ratios else 1.0
        bonus_growth = 0.0
        if avg_growth >= 1.25:
            bonus_growth = 1.0
        elif avg_growth >= 1.15:
            bonus_growth = 0.5

        raw = base_score + bonus_growth
        if team_score > opp_score:
            raw += 0.5  # Modest victory execution bonus

        return raw, {
            "style_name": arch.get("style_name", "標準バランス型"),
            "key_metrics": key_metrics,
            "percentile": round(avg_pct, 3),
            "growth_ratio": round(avg_growth, 2),
            "bonus_growth": bonus_growth,
            "raw_score": round(raw, 2),
        }

    def _calc_duels_intensity(
        self,
        t_flab: Dict[str, Any],
        players: List[Dict[str, Any]],
        team_score: int,
        opp_score: int,
    ) -> Tuple[float, Dict[str, Any]]:
        """4. Duels & Intensity (Raw Base)"""
        tackles_rate = float(t_flab.get("tackles_rate") or 60.0)
        cbp_gain = float(t_flab.get("cbp_gain") or 60.0)

        duels_won = sum(int(p.get("duels_won") or 0) for p in players)
        if duels_won == 0:
            duels_won = 20

        tackles = float(t_flab.get("tackles") or 0.0)
        intercepts = float(t_flab.get("intercepts") or 0.0)
        def_actions = tackles + intercepts
        opp_passes = float(t_flab.get("opponent_passes") or 350.0)
        proxy_ppda = opp_passes / max(def_actions, 1.0)

        s_tackle = (tackles_rate - 60.0) * 0.08
        s_duel = (duels_won - 20.0) * 0.12
        s_gain = (cbp_gain - 60.0) * 0.04
        s_ppda = (18.0 - min(proxy_ppda, 30.0)) * 0.10

        raw = 5.0 + s_tackle + s_duel + s_gain + s_ppda

        return raw, {
            "tackles_rate": tackles_rate,
            "duels_won": duels_won,
            "cbp_gain": cbp_gain,
            "proxy_ppda": round(proxy_ppda, 1),
            "raw_score": round(raw, 2),
        }

    def _calc_team_cohesion(
        self,
        t_flab: Dict[str, Any],
        players: List[Dict[str, Any]],
        team_score: int,
        opp_score: int,
    ) -> Tuple[float, Dict[str, Any]]:
        """5. Team Cohesion (Raw Base)"""
        fwd_passes = 0
        opp_half_passes = 0
        opp_half_success = 0
        for p in players:
            raw_str = p.get("raw_stats_json")
            if raw_str:
                try:
                    p_raw = json.loads(raw_str)
                    spaia = p_raw.get("spaia", {})
                    pf = spaia.get("pass_forward", {})
                    fwd_passes += int(pf.get("count") or 0)
                    opp_cnt = int(spaia.get("opp_area_pass_count") or 0)
                    opp_rate = float(spaia.get("opp_area_pass_rate") or 0.0)
                    opp_half_passes += opp_cnt
                    opp_half_success += int(opp_cnt * (opp_rate / 100.0))
                except Exception:
                    pass

        if fwd_passes == 0:
            fwd_passes = 120
        opp_pass_rate = (
            (opp_half_success / max(opp_half_passes, 1)) * 100.0
            if opp_half_passes > 0
            else float(t_flab.get("passes_rate") or 80.0)
        )

        touches = [float(p.get("touches") or 0.0) for p in players if float(p.get("touches") or 0.0) > 0]
        if len(touches) >= 3:
            tot_t = sum(touches)
            probs = [t / tot_t for t in touches]
            ent = -sum(pr * math.log2(pr) for pr in probs if pr > 0)
            entropy = ent / math.log2(len(touches))
        else:
            entropy = 0.85

        assists = sum(int(p.get("assists") or 0) for p in players)
        s_assist = 1.0 if assists >= 2 else (0.5 if assists == 1 else 0.0)

        s_fwd = (fwd_passes - 120.0) * 0.015
        s_opp = (opp_pass_rate - 70.0) * 0.07
        s_ent = (entropy - 0.85) * 4.0

        raw = 5.0 + s_fwd + s_opp + s_ent + s_assist

        return raw, {
            "forward_passes": fwd_passes,
            "opp_area_pass_rate": round(opp_pass_rate, 1),
            "touch_entropy": round(entropy, 3),
            "assists": assists,
            "raw_score": round(raw, 2),
        }

    def _calc_excitement_index(
        self,
        team_id: str,
        opp_id: str,
        team_score: int,
        opp_score: int,
        events: List[Dict[str, Any]],
        t_flab: Dict[str, Any],
        o_flab: Dict[str, Any],
        is_home: bool,
    ) -> Tuple[float, Dict[str, Any]]:
        """6. Excitement Index (Raw Base with Positive & Negative Penalties)"""
        bonuses = 0.0
        penalties = 0.0
        reasons = []

        derby_name = self.is_derby_match(team_id, opp_id)

        # ---------------------------------------------------------------------
        # Positive Factors (Victories & Thrilling Events)
        # ---------------------------------------------------------------------
        if derby_name and team_score > opp_score:
            bonuses += 1.5
            reasons.append(f"{derby_name}勝利 (+1.5)")

        # Red card events
        red_card_events = [e for e in events if e.get("event_type") == "red_card"]
        team_reds = [e for e in red_card_events if e.get("team_id") == team_id]
        if team_reds:
            red_min = team_reds[0].get("minute") or 0
            if team_score > opp_score:
                bonuses += 2.0
                reasons.append(f"退場発生({red_min}分)後の数的不利勝利 (+2.0)")
            elif team_score == opp_score:
                bonuses += 1.5
                reasons.append(f"退場発生({red_min}分)後の数的不利ドロー (+1.5)")

        # Timeline analysis for comeback, late goals, and blown leads
        running_t = 0
        running_o = 0
        was_trailing = False
        was_leading = False
        late_goal_scored = False
        late_goal_conceded = False

        for e in events:
            ev_type = e.get("event_type")
            ev_team = e.get("team_id")
            minute = int(e.get("minute") or 0)
            if ev_type == "goal":
                if ev_team == team_id:
                    running_t += 1
                else:
                    running_o += 1
                if running_o > running_t:
                    was_trailing = True
                if running_t > running_o:
                    was_leading = True
                if minute >= 80:
                    if ev_team == team_id:
                        late_goal_scored = True
                    else:
                        late_goal_conceded = True

        # Comeback win
        if was_trailing and team_score > opp_score:
            bonuses += 1.5
            reasons.append("ビハインドからの逆転勝利 (+1.5)")

        # Late dramatic goal
        if late_goal_scored and team_score >= opp_score:
            bonuses += 1.5
            reasons.append("80分以降の劇的ゴール (+1.5)")

        # Convincing win / Away win
        if team_score > opp_score:
            if (team_score - opp_score) >= 3:
                bonuses += 1.5
                reasons.append(f"{team_score}-{opp_score}の圧巻快勝劇 (+1.5)")
            elif not is_home:
                bonuses += 1.0
                reasons.append("敵地でのアウェイ白星 (+1.0)")

        # Goal shootout / high xG
        total_goals = team_score + opp_score
        if total_goals >= 4:
            bonuses += 1.0
            reasons.append(f"合計{total_goals}得点の乱打戦 (+1.0)")
        elif total_goals == 3:
            bonuses += 0.5
            reasons.append(f"合計{total_goals}得点の打ち合い (+0.5)")

        t_xg = float(t_flab.get("xg") or 0.0)
        o_xg = float(o_flab.get("xg") or 0.0)
        if (t_xg + o_xg) >= 3.0:
            bonuses += 0.5
            reasons.append(f"両チーム合計xG {round(t_xg+o_xg, 1)}の好機量産 (+0.5)")

        # High Intensity
        t_sprints = int(t_flab.get("sprints") or 0)
        o_sprints = int(o_flab.get("sprints") or 0)
        if (t_sprints + o_sprints) >= 240:
            bonuses += 0.5
            reasons.append("激しいスプリント攻防 (+0.5)")

        # ---------------------------------------------------------------------
        # Negative Factors (Frustrations & Painful Failures)
        # ---------------------------------------------------------------------
        # A. Blown Lead / Comeback defeat
        if was_leading and team_score < opp_score:
            penalties += 1.5
            reasons.append("先制・リードからの逆転負け (-1.5)")

        # B. Late dramatic goal conceded
        if late_goal_conceded and team_score <= opp_score:
            penalties += 1.5
            reasons.append("85分以降の痛恨の被弾 (-1.5)")

        # C. Self-destruction via red card in defeat
        if team_reds and team_score < opp_score:
            penalties += 1.5
            reasons.append("自チーム退場による自滅・敗戦 (-1.5)")

        # D. Derby Defeat
        if derby_name and team_score < opp_score:
            penalties += 1.0
            reasons.append(f"{derby_name}敗戦の屈辱 (-1.0)")

        # E. Demolition defeat (3+ goal margin)
        if (opp_score - team_score) >= 3:
            penalties += 1.5
            reasons.append(f"{team_score}-{opp_score}のショッキングな大敗 (-1.5)")

        # F. Home shutout defeat
        if is_home and team_score == 0 and opp_score > 0:
            penalties += 0.5
            reasons.append("本拠地での完封負け (-0.5)")

        # G. Bore draw penalty
        t_sot = int(t_flab.get("shots_on_target") or 0)
        o_sot = int(o_flab.get("shots_on_target") or 0)
        if total_goals == 0 and (t_sot + o_sot) <= 4:
            penalties += 2.0
            reasons.append("決定機僅少の0-0膠着戦 (-2.0)")

        raw = 5.0 + bonuses - penalties

        return raw, {
            "bonuses": round(bonuses, 2),
            "penalties": round(penalties, 2),
            "reasons": reasons,
            "raw_score": round(raw, 2),
        }

    def _determine_rank(self, total: int) -> str:
        """S to D grade mapping according to El Golasso standard."""
        if total >= 49:
            return "S"
        if total >= 43:
            return "A+"
        if total >= 37:
            return "A-"
        if total >= 31:
            return "B+"
        if total >= 25:
            return "B-"
        if total >= 13:
            return "C"
        return "D"

    def generate_critique(
        self,
        report_card: Dict[str, Any],
    ) -> Dict[str, str]:
        """Generate El Golasso-style reporter critique and headline."""
        rank = report_card.get("rank", "B+")
        total_score = report_card.get("total_score", 30)
        score_str = report_card.get("score", "0-0")
        is_home = report_card.get("is_home", True)
        metrics = report_card.get("metrics", {})

        # Parse score
        parts = score_str.split("-")
        t_score = int(parts[0]) if len(parts) == 2 else 0
        o_score = int(parts[1]) if len(parts) == 2 else 0

        # Sort metrics by score
        metric_items = [
            (k, v.get("name", k), v.get("score", 0), v.get("details", {}))
            for k, v in metrics.items()
        ]
        metric_items.sort(key=lambda x: x[2], reverse=True)

        best_m = metric_items[0] if metric_items else ("none", "総合", 5, {})
        worst_m = metric_items[-1] if metric_items else ("none", "総合", 5, {})

        # Excitement reasons if any
        exc_reasons = (
            metrics.get("excitement_index", {})
            .get("details", {})
            .get("reasons", [])
        )

        # Headlines by rank
        headline_map = {
            "S": "【最高評価 S】敵陣を完全制圧。戦術遂行と気迫が結実した圧巻の勝利",
            "A+": "【高評価 A+】高い完成度と球際強度で相手を凌駕。手応え十分の白星",
            "A-": "【好評価 A-】主導権を握り要所を締める。狙い通りの試合運びを披露",
            "B+": "【及第点 B+】激しい攻防の中で粘り強さを発揮。収穫の多い戦い",
            "B-": "【課題残す B-】随所に好機を作るも詰めを欠く。次節への修正が焦点",
            "C": "【苦杯 C】相手の圧力に後手を踏み、最後まで主導権を取り戻せず",
            "D": "【完敗 D】攻守に精彩を欠き厳しい内容。組織全体の建て直しが急務",
        }
        headline = headline_map.get(rank, f"【評価 {rank}】総得点 {total_score}点の戦い")

        # Context summary
        loc_str = "本拠地" if is_home else "アウェイ"
        if t_score > o_score:
            res_str = f"{loc_str}で{t_score}-{o_score}の白星。"
        elif t_score == o_score:
            res_str = f"{loc_str}で{t_score}-{o_score}のドロー決着。"
        else:
            res_str = f"{loc_str}で{t_score}-{o_score}の敗戦。"

        # Highlights
        pos_notes = []
        if best_m[2] >= 7:
            clean_name = (
                best_m[1]
                .replace("①", "")
                .replace("②", "")
                .replace("③", "")
                .replace("④", "")
                .replace("⑤", "")
                .replace("⑥", "")
            )
            pos_notes.append(f"「{clean_name}」で高い水準（{best_m[2]}/10点）を発揮")

        if exc_reasons:
            clean_reasons = [r.split(" (")[0] for r in exc_reasons if "+" in r]
            if clean_reasons:
                pos_notes.append(f"{'・'.join(clean_reasons[:2])}などドラマ性も際立った")

        neg_notes = []
        if worst_m[2] <= 4:
            clean_worst = (
                worst_m[1]
                .replace("①", "")
                .replace("②", "")
                .replace("③", "")
                .replace("④", "")
                .replace("⑤", "")
                .replace("⑥", "")
            )
            neg_notes.append(f"「{clean_worst}」（{worst_m[2]}/10点）に改善の余地を残す")

        body_parts = [res_str]
        if pos_notes:
            body_parts.append(f"とりわけ{'、'.join(pos_notes)}。")
        if neg_notes:
            body_parts.append(f"一方で{'、'.join(neg_notes)}。")
        else:
            body_parts.append("全項目で破綻なくバランスの取れたパフォーマンスを披露した。")

        text = "".join(body_parts)

        return {
            "headline": headline,
            "text": text,
            "best_metric": best_m[1],
            "worst_metric": worst_m[1],
        }
