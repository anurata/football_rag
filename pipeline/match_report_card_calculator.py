# -*- coding: utf-8 -*-
"""
Match Report Card Calculator (pipeline/match_report_card_calculator.py).
Calculates the 6-dimension report card (Game Dominance, Individual Power,
Style Execution, Duels & Intensity, Team Cohesion, Excitement Index)
conforming to docs/MATCH_REPORT_CARD_SPECIFICATION.md and El Golasso's
reporter scorecard standard.
Tuned with outcome-anchored adjustments and empirical data baselines.
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

    def calculate_report_card(
        self,
        match_id: str,
        team_id: str,
    ) -> Dict[str, Any]:
        """Calculate complete 6-metric report card for target team in specified match."""
        with get_db_connection(self.db_path) as conn:
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

        # 6. Calculate 6 Dimensions with Outcome Integration
        score_1, details_1 = self._calc_game_dominance(
            t_flab=t_flab,
            o_flab=o_flab,
            team_score=team_score,
            opp_score=opp_score,
        )
        score_2, details_2 = self._calc_individual_power(
            t_flab=t_flab,
            players=players,
            team_score=team_score,
            opp_score=opp_score,
        )
        score_3, details_3 = self._calc_style_execution(
            team_id=team_id,
            t_flab=t_flab,
            mw_stats=mw_stats,
            team_score=team_score,
            opp_score=opp_score,
        )
        score_4, details_4 = self._calc_duels_intensity(
            t_flab=t_flab,
            players=players,
            team_score=team_score,
            opp_score=opp_score,
        )
        score_5, details_5 = self._calc_team_cohesion(
            t_flab=t_flab,
            players=players,
            team_score=team_score,
            opp_score=opp_score,
        )
        score_6, details_6 = self._calc_excitement_index(
            team_id=team_id,
            opp_id=opp_id,
            team_score=team_score,
            opp_score=opp_score,
            events=events,
            t_flab=t_flab,
            o_flab=o_flab,
            is_home=is_home,
        )

        raw_total = score_1 + score_2 + score_3 + score_4 + score_5 + score_6
        total_score = self._calibrate_total_score(raw_total, team_score, opp_score)
        rank = self._determine_rank(total_score)

        return {
            "match_id": match_id,
            "team_id": team_id,
            "opp_team_id": opp_id,
            "is_home": is_home,
            "score": f"{team_score}-{opp_score}",
            "total_score": total_score,
            "rank": rank,
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

    # -------------------------------------------------------------------------
    # Dimension Calculators
    # -------------------------------------------------------------------------

    def _calc_game_dominance(
        self,
        t_flab: Dict[str, Any],
        o_flab: Dict[str, Any],
        team_score: int,
        opp_score: int,
    ) -> Tuple[int, Dict[str, Any]]:
        """1. Game Dominance (0-10)

        Anchored to pitch territory, xG suppress and actual goal difference.
        """
        poss = float(t_flab.get("possession_rate") or 50.0)
        t_m30 = float(t_flab.get("m30_entries") or 0.0)
        o_m30 = float(o_flab.get("m30_entries") or 0.0)
        field_tilt = (t_m30 / max(t_m30 + o_m30, 1.0)) * 100.0

        t_xg = float(t_flab.get("xg") or 0.0)
        o_xg = float(o_flab.get("xg") or 0.0)
        xg_diff = t_xg - o_xg

        goal_diff = team_score - opp_score

        s_poss = (poss - 50.0) * 0.06
        s_tilt = (field_tilt - 50.0) * 0.04
        s_suppress = xg_diff * 0.6
        s_result = goal_diff * 0.5  # Outcome anchor

        raw = 5.0 + s_poss + s_tilt + s_suppress + s_result
        if opp_score == 0 and team_score > 0:
            raw += 0.5  # Clean sheet victory bonus

        final = max(0, min(10, round(raw)))

        return final, {
            "possession_rate": poss,
            "field_tilt": round(field_tilt, 1),
            "xg_diff": round(xg_diff, 2),
            "goal_diff": goal_diff,
            "raw_score": round(raw, 2),
        }

    def _calc_individual_power(
        self,
        t_flab: Dict[str, Any],
        players: List[Dict[str, Any]],
        team_score: int,
        opp_score: int,
    ) -> Tuple[int, Dict[str, Any]]:
        """2. Individual Power (0-10)"""
        dribbles = float(t_flab.get("dribbles") or 0.0)
        drib_rate = float(t_flab.get("dribbles_rate") or 0.0)
        drib_succ = dribbles * (drib_rate / 100.0)

        # Max player rating and individual scoring brilliance
        ratings = []
        max_goals_by_single_player = 0
        for p in players:
            g = int(p.get("goals") or 0)
            if g > max_goals_by_single_player:
                max_goals_by_single_player = g
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

        # Sub impact
        bench = [p for p in players if not p.get("is_starter") and (p.get("minutes_played") or 0) > 0]
        sub_mva = sum(float(p.get("xg") or 0.0) + float(p.get("xa") or 0.0) for p in bench)

        s_drib = (drib_succ - 6.0) * 0.15
        s_rating = (max_rating - 6.0) * 1.0
        s_threat = (non_shot_obv - 1.5) * 0.25
        s_sub = min(sub_mva * 0.8, 1.0)
        s_individual_goals = 1.0 if max_goals_by_single_player >= 2 else (0.5 if max_goals_by_single_player == 1 else 0.0)

        raw = 5.0 + s_drib + s_rating + s_threat + s_sub + s_individual_goals
        final = max(0, min(10, round(raw)))

        return final, {
            "dribble_success": round(drib_succ, 1),
            "max_player_rating": max_rating,
            "max_single_goals": max_goals_by_single_player,
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
    ) -> Tuple[int, Dict[str, Any]]:
        """3. Tactical Style Execution (0-10)

        Base: Percentile rank across league matches
        Bonus: Growth exceeding own team's season average
        Anchor: Victory bonus (+1.0) or Heavy Loss Cap (max 5 for >=3 goal defeat)
        """
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

        # Growth bonus
        avg_growth = sum(growth_ratios) / max(len(growth_ratios), 1) if growth_ratios else 1.0
        bonus_growth = 0.0
        if avg_growth >= 1.25:
            bonus_growth = 1.0
        elif avg_growth >= 1.15:
            bonus_growth = 0.5

        raw = base_score + bonus_growth

        # Result alignment
        if team_score > opp_score:
            raw += 0.8  # Style led to victory
        elif (opp_score - team_score) >= 3:
            raw = min(raw, 5.0)  # Cannot claim style success when demolished

        final = max(0, min(10, round(raw)))

        return final, {
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
    ) -> Tuple[int, Dict[str, Any]]:
        """4. Duels & Intensity (0-10)

        Tuned to empirical J1 player duel median (~20 duels won per team).
        """
        tackles_rate = float(t_flab.get("tackles_rate") or 60.0)
        cbp_gain = float(t_flab.get("cbp_gain") or 60.0)

        # duels won (actual median in DB is ~20)
        duels_won = sum(int(p.get("duels_won") or 0) for p in players)
        if duels_won == 0:
            duels_won = 20  # empirical fallback default

        # proxy ppda
        tackles = float(t_flab.get("tackles") or 0.0)
        intercepts = float(t_flab.get("intercepts") or 0.0)
        def_actions = tackles + intercepts
        opp_passes = float(t_flab.get("opponent_passes") or 350.0)
        proxy_ppda = opp_passes / max(def_actions, 1.0)

        s_tackle = (tackles_rate - 60.0) * 0.08
        s_duel = (duels_won - 20.0) * 0.12  # Tuned around 20 duels
        s_gain = (cbp_gain - 60.0) * 0.04
        s_ppda = (18.0 - min(proxy_ppda, 30.0)) * 0.10

        raw = 5.0 + s_tackle + s_duel + s_gain + s_ppda
        final = max(0, min(10, round(raw)))

        return final, {
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
    ) -> Tuple[int, Dict[str, Any]]:
        """5. Team Cohesion (0-10)"""
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
        final = max(0, min(10, round(raw)))

        return final, {
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
    ) -> Tuple[int, Dict[str, Any]]:
        """6. Excitement Index (0-10)"""
        bonuses = 0.0
        bonus_reasons = []

        # A. Derby Match
        derby_name = self.is_derby_match(team_id, opp_id)
        if derby_name and team_score > opp_score:
            bonuses += 1.5
            bonus_reasons.append(f"{derby_name}勝利 (+1.5)")

        # B. Red card drama (numerical disadvantage)
        red_card_events = [e for e in events if e.get("event_type") == "red_card"]
        team_reds = [e for e in red_card_events if e.get("team_id") == team_id]
        if team_reds:
            red_min = team_reds[0].get("minute") or 0
            if team_score > opp_score:
                bonuses += 2.0
                bonus_reasons.append(f"退場者発生({red_min}分)後の数的不利勝利 (+2.0)")
            elif team_score == opp_score:
                bonuses += 1.5
                bonus_reasons.append(f"退場者発生({red_min}分)後の数的不利ドロー (+1.5)")

        # C. Comeback win (Trailing to Win)
        running_t = 0
        running_o = 0
        was_trailing = False
        late_goal = False
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
                if minute >= 80 and ev_team == team_id and running_t >= running_o:
                    late_goal = True

        if was_trailing and team_score > opp_score:
            bonuses += 1.5
            bonus_reasons.append("ビハインドからの逆転勝利 (+1.5)")

        # D. Late dramatic goal
        if late_goal and team_score >= opp_score:
            bonuses += 1.5
            bonus_reasons.append("80分以降の劇的ゴール (+1.5)")

        # E. Convincing win / Away win
        if team_score > opp_score:
            if (team_score - opp_score) >= 3:
                bonuses += 1.5
                bonus_reasons.append(f"{team_score}-{opp_score}の圧巻快勝劇 (+1.5)")
            elif not is_home:
                bonuses += 1.0
                bonus_reasons.append("敵地でのアウェイ白星 (+1.0)")

        # F. Goal shootout / high xG
        total_goals = team_score + opp_score
        if total_goals >= 4:
            bonuses += 1.0
            bonus_reasons.append(f"合計{total_goals}得点の乱打戦 (+1.0)")
        elif total_goals == 3:
            bonuses += 0.5
            bonus_reasons.append(f"合計{total_goals}得点の打ち合い (+0.5)")

        t_xg = float(t_flab.get("xg") or 0.0)
        o_xg = float(o_flab.get("xg") or 0.0)
        if (t_xg + o_xg) >= 3.0:
            bonuses += 0.5
            bonus_reasons.append(f"両チーム合計xG {round(t_xg+o_xg, 1)}の好機量産 (+0.5)")

        # G. High Intensity
        t_sprints = int(t_flab.get("sprints") or 0)
        o_sprints = int(o_flab.get("sprints") or 0)
        if (t_sprints + o_sprints) >= 240:
            bonuses += 0.5
            bonus_reasons.append("激しいスプリント攻防 (+0.5)")

        # H. Bore draw penalty
        penalty = 0.0
        t_sot = int(t_flab.get("shots_on_target") or 0)
        o_sot = int(o_flab.get("shots_on_target") or 0)
        if total_goals == 0 and (t_sot + o_sot) <= 4:
            penalty = 2.0
            bonus_reasons.append("決定機僅少の0-0膠着戦 (-2.0)")

        raw = 5.0 + bonuses - penalty
        final = max(0, min(10, round(raw)))

        return final, {
            "bonuses": round(bonuses, 2),
            "penalty": penalty,
            "reasons": bonus_reasons,
            "raw_score": round(raw, 2),
        }

    def _calibrate_total_score(
        self,
        raw_total: int,
        team_score: int,
        opp_score: int,
    ) -> int:
        """Outcome alignment calibration to maintain reporter-grade consistency."""
        tot = raw_total
        if team_score > opp_score:
            # Victory floor guarantees at least A- (37)
            tot = max(tot, 37)
            if (team_score - opp_score) >= 2:
                tot = max(tot, 42)
        elif team_score < opp_score:
            # Defeat cap: cannot receive A+ (43+) on defeat
            if (opp_score - team_score) >= 2:
                tot = min(tot, 32)
            else:
                tot = min(tot, 36)
        else:
            # Draw cap: draws do not reach A+ (max 38 A-)
            tot = min(tot, 38)
        return max(0, min(60, tot))

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
