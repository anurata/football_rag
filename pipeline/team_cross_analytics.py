# -*- coding: utf-8 -*-
"""
Team Cross-Analytics & Opponent Clustering Engine.
(pipeline/team_cross_analytics.py)

Implements generalized multi-axis cross-analytics for any J1 club:
1. Dynamic 15-Minute Segment Analytics (Time-slice event matrix)
2. Starter Unit Synergy Quantification (CB, DH pairs)
3. Opponent Defensive Archetype Clustering & Resistance Matrix
   (High-Press vs Middle-Block vs Low-Block)
Persists analytical models into structured JSON for downstream RAG,
Curation, and Matchday Forecasting.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from pipeline.team_55_metrics_calculator import Team55MetricsCalculator


class TeamCrossAnalyticsEngine:
    """Generalized engine for time-segment dynamics, starter synergy, and opponent archetype resilience."""

    def __init__(self, team_id: str = "FCT", db_path: Path = DEFAULT_DB_PATH) -> None:
        self.team_id = team_id.upper()
        self.db_path = db_path
        self.metrics_calc = Team55MetricsCalculator(team_id=self.team_id, db_path=db_path)

    # -------------------------------------------------------------------------
    # 1. Dynamic 15-Minute Time-Segment Analytics
    # -------------------------------------------------------------------------

    def compute_time_segment_dynamics(
        self,
        conn: sqlite3.Connection,
        match_ids: List[str],
    ) -> Dict[str, Any]:
        """Aggregate events into 6 standardized 15-minute segments across all matches."""
        segments = ["0-15", "16-30", "31-45+", "46-60", "61-75", "76-90+"]
        matrix: Dict[str, Dict[str, Any]] = {
            seg: {
                "team_goals": 0,
                "opp_goals": 0,
                "team_shots_missed": 0,
                "opp_shots_missed": 0,
                "team_cards": 0,
                "opp_cards": 0,
                "team_total_xg": 0.0,
                "opp_total_xg": 0.0,
                # Backwards-compatibility aliases for FCT
                "fct_goals": 0,
                "fct_shots_missed": 0,
                "fct_cards": 0,
                "fct_total_xg": 0.0,
            }
            for seg in segments
        }

        def get_seg(minute: int, period: str) -> str:
            # 2Hでminuteが45以下の場合は通算時間（+45分）に補正
            actual_m = minute
            if period == "2H" and actual_m <= 45:
                actual_m += 45

            if actual_m <= 15:
                return "0-15"
            elif actual_m <= 30:
                return "16-30"
            elif actual_m <= 45:
                return "31-45+"
            elif actual_m <= 60:
                return "46-60"
            elif actual_m <= 75:
                return "61-75"
            else:
                return "76-90+"

        if not match_ids:
            return matrix

        placeholders = ",".join(["?"] * len(match_ids))
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT match_id, minute, period, team_id, event_type, xg, description_text
            FROM match_events
            WHERE match_id IN ({placeholders})
            ORDER BY minute ASC;
            """,
            match_ids,
        )
        events = cur.fetchall()

        for ev in events:
            m = ev["minute"] or 0
            period = ev.get("period") or "1H"
            seg = get_seg(m, period)
            is_target_team = (ev["team_id"] == self.team_id)
            desc = ev["description_text"] or ""
            xg_val = float(ev["xg"] or 0.0)

            is_goal = ("GOOOOOAL!!" in desc) or (
                ("得点" in desc or "ゴールを決める" in desc or "ネットを揺らす" in desc)
                and not any(neg in desc for neg in ["外れる", "外れてしまう", "セーブ", "期待値", "シュート数", "ここまでのシュート", "枠上", "枠外"])
            )

            if is_goal:
                if is_target_team:
                    matrix[seg]["team_goals"] += 1
                    matrix[seg]["fct_goals"] += 1
                else:
                    matrix[seg]["opp_goals"] += 1
            elif "外れる" in desc or "セーブ" in desc or ev["event_type"] == "SHOT":
                if is_target_team:
                    matrix[seg]["team_shots_missed"] += 1
                    matrix[seg]["fct_shots_missed"] += 1
                else:
                    matrix[seg]["opp_shots_missed"] += 1
            elif ev["event_type"] in ("YELLOW_CARD", "RED_CARD"):
                if is_target_team:
                    matrix[seg]["team_cards"] += 1
                    matrix[seg]["fct_cards"] += 1
                else:
                    matrix[seg]["opp_cards"] += 1

            if is_target_team:
                matrix[seg]["team_total_xg"] = round(matrix[seg]["team_total_xg"] + xg_val, 2)
                matrix[seg]["fct_total_xg"] = round(matrix[seg]["fct_total_xg"] + xg_val, 2)
            else:
                matrix[seg]["opp_total_xg"] = round(matrix[seg]["opp_total_xg"] + xg_val, 2)

        return matrix

    # -------------------------------------------------------------------------
    # 2. Starter Unit Synergy Quantification
    # -------------------------------------------------------------------------

    def compute_starter_unit_synergy(
        self,
        conn: sqlite3.Connection,
        match_metrics: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Quantify tactical synergy for starter player combinations."""
        cur = conn.cursor()
        match_ids = [m["試合ID"] for m in match_metrics]
        if not match_ids:
            return {
                "center_back_units": [],
                "central_midfield_units": [],
            }

        placeholders = ",".join(["?"] * len(match_ids))
        cur.execute(
            f"""
            SELECT match_id, player_name, position, number, is_starter
            FROM player_match_stats
            WHERE match_id IN ({placeholders}) AND team_id = ? AND is_starter = 1
            ORDER BY match_id ASC, position ASC, number ASC;
            """,
            match_ids + [self.team_id],
        )
        starters = cur.fetchall()

        starters_by_match = defaultdict(list)
        for s in starters:
            starters_by_match[s["match_id"]].append(s)

        metrics_map = {m["試合ID"]: m for m in match_metrics}

        cb_pairs = defaultdict(list)
        dh_pairs = defaultdict(list)

        for m_id, s_list in starters_by_match.items():
            cbs = sorted([p["player_name"] for p in s_list if p["position"] == "DF"])
            mfs = sorted([p["player_name"] for p in s_list if p["position"] == "MF"])

            m_data = metrics_map.get(m_id, {})
            hull = m_data.get("31_チーム凸包面積(㎡)", 1200.0)
            xpts = m_data.get("43_ポアソン期待勝点(xPTS)", 1.5)
            pts = m_data.get("獲得勝点", 1)

            # Extract 2 primary central defenders
            if len(cbs) >= 2:
                pair_key = f"{cbs[0]} × {cbs[1]}"
                cb_pairs[pair_key].append({
                    "m_id": m_id,
                    "pts": pts,
                    "xpts": xpts,
                    "hull": hull,
                })

            # Extract primary central midfielders
            if len(mfs) >= 2:
                dh_key = f"{mfs[0]} × {mfs[1]}"
                dh_pairs[dh_key].append({
                    "m_id": m_id,
                    "pts": pts,
                    "xpts": xpts,
                    "hull": hull,
                })

        def summarize_units(unit_dict: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
            res = []
            for name, games in unit_dict.items():
                count = len(games)
                avg_pts = round(sum(g["pts"] for g in games) / count, 2)
                avg_xpts = round(sum(g["xpts"] for g in games) / count, 2)
                avg_hull = round(sum(g["hull"] for g in games) / count, 1)
                win_count = sum(1 for g in games if g["pts"] == 3)
                win_rate = round(win_count / count * 100.0, 1)
                res.append({
                    "unit_name": name,
                    "matches_played": count,
                    "win_rate_pct": win_rate,
                    "avg_actual_pts": avg_pts,
                    "avg_xpts": avg_xpts,
                    "avg_convex_hull_m2": avg_hull,
                })
            return sorted(res, key=lambda x: x["matches_played"], reverse=True)

        return {
            "center_back_units": summarize_units(cb_pairs),
            "central_midfield_units": summarize_units(dh_pairs),
        }

    # -------------------------------------------------------------------------
    # 3. Opponent Archetype Clustering & Resistance Matrix
    # -------------------------------------------------------------------------

    def classify_opponent_archetype(
        self,
        opp_flab: Dict[str, Any],
    ) -> Tuple[str, str]:
        """Classify opponent into High-Press, Middle-Block, or Low-Block."""
        opp_poss = float(opp_flab.get("possession_rate") or 50.0)
        opp_clears = int(opp_flab.get("clears") or 0)
        opp_tackles = int(opp_flab.get("tackles") or 0)

        # 1. Low-Block archetype: Low possession (< 45%) and heavy clears (>= 20)
        if opp_poss < 45.0 and opp_clears >= 20:
            return "LOW_BLOCK", "低重心ブロック・撤退カウンター型（自陣籠城＆ロングカウンター）"
        # 2. High-Press archetype: Aggressive tackling and active attempts to challenge
        elif opp_tackles >= 18 or (opp_poss >= 48.0 and opp_clears <= 16):
            return "HIGH_PRESS", "ハイプレス志向型（前線からのボール狩り＆ショートカウンター）"
        # 3. Middle-Block archetype: balanced possession and zone containment
        else:
            return "MID_BLOCK", "ミドルブロック・構造的陣形管理型（中盤での迎撃＆ポゼッション）"

    def compute_opponent_resistance_matrix(
        self,
        conn: sqlite3.Connection,
        match_metrics: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Analyze team performance grouped by opponent tactical archetypes."""
        cur = conn.cursor()
        archetype_groups = defaultdict(list)

        for m_data in match_metrics:
            m_id = m_data["試合ID"]
            opp_id = m_data["対戦相手"]

            cur.execute("SELECT * FROM team_match_flab_stats WHERE match_id = ? AND team_id = ?", (m_id, opp_id))
            opp_flab = cur.fetchone() or {}

            arch_code, arch_desc = self.classify_opponent_archetype(opp_flab)
            conv_rate = m_data.get("13_30m→PA進入変換率(%)") or m_data.get("05_30m→PA進入変換率(%)") or 0.0
            cross_rate = m_data.get("14_攻撃経路クロス依存度(%)") or m_data.get("03_サイド偏重度(クロス依存率%)") or 0.0

            archetype_groups[arch_code].append({
                "match_id": m_id,
                "opp_id": opp_id,
                "archetype_desc": arch_desc,
                "score": m_data["実スコア"],
                "pts": m_data["獲得勝点"],
                "xpts": m_data.get("43_ポアソン期待勝点(xPTS)", 1.5),
                "bpi": m_data.get("48_BPI(ボール前進総合指数)", 100.0),
                "conv_30_to_pa": conv_rate,
                "cross_reliance": cross_rate,
                "xt_approx": m_data.get("39_ゾーン別期待脅威度(xT近似)", 0.5),
                "convex_hull": m_data.get("31_チーム凸包面積(㎡)", 1200.0),
            })

        matrix = {}
        for arch, games in archetype_groups.items():
            count = len(games)
            matrix[arch] = {
                "description": games[0]["archetype_desc"],
                "match_count": count,
                "matches": [f"{g['opp_id']} ({g['score']})" for g in games],
                "matches_raw": games,
                "win_rate_pct": round(sum(1 for g in games if g["pts"] == 3) / count * 100.0, 1),
                "avg_xpts": round(sum(g["xpts"] for g in games) / count, 2),
                "avg_conv_30_to_pa_pct": round(sum(g["conv_30_to_pa"] for g in games) / count, 1),
                "avg_cross_reliance_pct": round(sum(g["cross_reliance"] for g in games) / count, 1),
                "avg_xt_approx": round(sum(g["xt_approx"] for g in games) / count, 2),
                "avg_bpi": round(sum(g["bpi"] for g in games) / count, 1),
            }

        return matrix

    def enrich_structured_match_files(
        self,
        opponent_resistance: Dict[str, Any],
    ) -> int:
        """Enrich each match tactical JSON in data/structured/ with opponent archetype and cross context."""
        structured_dir = ROOT_DIR / "data" / "structured"
        enriched_count = 0

        # Create mapping of match_id -> archetype info
        match_arch_map = {}
        for arch_code, data in opponent_resistance.items():
            for g in data.get("matches_raw", []):
                match_arch_map[g["match_id"]] = {
                    "archetype_code": arch_code,
                    "archetype_description": data["description"],
                }

        for json_path in structured_dir.glob("*_tactical.json"):
            m_id = json_path.stem.replace("_tactical", "")
            if m_id in match_arch_map:
                try:
                    match_data = json.loads(json_path.read_text(encoding="utf-8"))
                    arch_info = match_arch_map[m_id]
                    match_data["opponent_tactical_archetype"] = {
                        "code": arch_info["archetype_code"],
                        "description": arch_info["archetype_description"],
                    }
                    json_path.write_text(json.dumps(match_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    enriched_count += 1
                except Exception:
                    pass

        return enriched_count

    # -------------------------------------------------------------------------
    # 4. Master Orchestration & Persistence
    # -------------------------------------------------------------------------

    def run_and_persist_synthesis(
        self,
        output_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute full cross-analytics and persist to structured storage."""
        conn = get_db_connection(str(self.db_path))
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        match_metrics = self.metrics_calc.calculate_all_matches()
        match_ids = [m["試合ID"] for m in match_metrics]

        # 1. 15-Minute Segment Matrix
        time_segments = self.compute_time_segment_dynamics(conn, match_ids)

        # 2. Starter Synergy
        unit_synergy = self.compute_starter_unit_synergy(conn, match_metrics)

        # 3. Opponent Archetype Resistance
        opponent_resistance = self.compute_opponent_resistance_matrix(conn, match_metrics)

        # 4. Enrich structured match files
        enriched_files = self.enrich_structured_match_files(opponent_resistance)

        conn.close()

        payload = {
            "meta": {
                "team_id": self.team_id,
                "season": 2026,
                "analyzed_matches": len(match_ids),
                "enriched_match_files": enriched_files,
                "matchweeks": [m["節"] for m in match_metrics],
            },
            "time_segment_dynamics": time_segments,
            "starter_unit_synergy": unit_synergy,
            "opponent_archetype_resistance": opponent_resistance,
        }

        if output_path is None:
            if self.team_id == "FCT":
                output_path = ROOT_DIR / "data" / "structured" / "fctokyo_season_tactical_synthesis.json"
            else:
                output_path = ROOT_DIR / "data" / "structured" / f"{self.team_id.lower()}_season_tactical_synthesis.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[SUCCESS] Persisted Season Tactical Synthesis for {self.team_id} at: {output_path}")

        return payload


# -----------------------------------------------------------------------------
# Backwards-Compatibility Alias
# -----------------------------------------------------------------------------
class FCTokyoCrossAnalyticsEngine(TeamCrossAnalyticsEngine):
    """Backwards-compatible subclass specifically for FC Tokyo."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        super().__init__(team_id="FCT", db_path=db_path)


if __name__ == "__main__":
    t_id = sys.argv[1] if len(sys.argv) > 1 else "FCT"
    engine = TeamCrossAnalyticsEngine(team_id=t_id)
    data = engine.run_and_persist_synthesis()
    print(f"\n[Time Segment Summary for {t_id.upper()}]")
    for seg, st in data["time_segment_dynamics"].items():
        print(f"  {seg}: Goals {st['team_goals']}-{st['opp_goals']}, Shots Missed {st['team_shots_missed']}")
    print(f"\n[Opponent Archetype Summary for {t_id.upper()}]")
    for arch, val in data["opponent_archetype_resistance"].items():
        print(f"  {arch} ({val['match_count']} games): WinRate {val['win_rate_pct']}%, Conv30toPA {val['avg_conv_30_to_pa_pct']}%, CrossReliance {val['avg_cross_reliance_pct']}%")

