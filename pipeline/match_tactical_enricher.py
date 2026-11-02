# -*- coding: utf-8 -*-
"""
Deterministic Match Tactical Enricher (pipeline/match_tactical_enricher.py).
Strictly conforms to TACTICAL_PHILOSOPHY_AND_MANIFESTO.md.

Eliminates Outcome Bias (結果バイアス):
Distinguishes tactical process/intent success from scoreline reality.
1. Base Style (Layer 2 Heuristics) & Matchday Plan
2. Pitch Clash & Tactical Performance (Layer 3 Grounded Explanation)
3. Content vs Result Discrepancy & Structural Outcome (Layer 4 Hypothesis & Truth)
4. Decisive Goals & Milestones
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.objective_profiler import resolve_team_name, TEAM_NAME_MAP
from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from scripts.calculate_match_context import MatchContextCalculator

logger = logging.getLogger("match_tactical_enricher")
ROOT_DIR = Path(__file__).resolve().parent.parent
PROFILES_PATH = ROOT_DIR / "knowledge" / "team_tactical_profiles.json"


class DeterministicTacticalEnricher:
    """Builds deep tactical structures grounded in knowledge profiles and match stats."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        profiles_path: Path = PROFILES_PATH,
    ) -> None:
        self.db_path = Path(db_path)
        self.profiles = self._load_team_profiles(profiles_path)
        self.context_calculator = MatchContextCalculator(db_path=Path(db_path))

    def _load_team_profiles(self, path: Path) -> Dict[str, Any]:
        """Load tactical profiles master for all 20 clubs."""
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("teams", {})
            except Exception as e:
                logger.warning("Failed to load tactical profiles from %s: %s", path, e)
        return {}

    def enrich_all_matches(
        self,
        output_dir: Path = ROOT_DIR / "data" / "structured",
    ) -> int:
        """Enrich all played 2026 matches with high-fidelity tactical structures."""
        output_dir.mkdir(parents=True, exist_ok=True)
        conn = get_db_connection(str(self.db_path))
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT match_id, season, matchweek, date, home_team_id, away_team_id,
                   home_score, away_score, stadium, weather
            FROM matches
            WHERE season = 2026
            ORDER BY matchweek ASC, date ASC;
            """
        )
        matches = cursor.fetchall()
        count = 0

        for m in matches:
            m_id = m["match_id"]
            out_file = output_dir / f"{m_id}_tactical.json"

            # Check if canonical high-fidelity file already exists (e.g. FCT canonical matches)
            if out_file.exists():
                try:
                    existing = json.loads(out_file.read_text(encoding="utf-8"))
                    # Preserve curated canonical FCT matches with rich human reviews
                    if existing.get("match_context") and ("FCT" in m_id):
                        continue
                except Exception:
                    pass

            tactical_struct = self.generate_match_tactical_structure(conn, m)
            out_file.write_text(
                json.dumps(tactical_struct, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            count += 1

        conn.close()
        logger.info("Successfully enriched %d matches with deep tactical analytics.", count)
        return count

    def generate_match_tactical_structure(
        self,
        conn: sqlite3.Connection,
        m: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Construct match-specific tactical structure for a single match."""
        m_id = m["match_id"]
        h_id = m["home_team_id"]
        a_id = m["away_team_id"]
        h_name = resolve_team_name(h_id)
        a_name = resolve_team_name(a_id)
        h_score = m.get("home_score", 0) or 0
        a_score = m.get("away_score", 0) or 0

        flab_h, flab_a = self._fetch_flab_stats(conn, m_id, h_id, a_id)
        formations = self._fetch_formations(conn, m_id, h_id, a_id)
        events = self._fetch_events(conn, m_id)

        deep_metrics = self._calculate_deep_metrics(flab_h, flab_a, h_score, a_score)

        # Synthesize tactical narrative using Layer 2 Knowledge & Layer 1 Facts
        highlights = self._synthesize_tactical_highlights(
            h_id=h_id,
            a_id=a_id,
            h_name=h_name,
            a_name=a_name,
            h_score=h_score,
            a_score=a_score,
            formations=formations,
            flab_h=flab_h,
            flab_a=flab_a,
            deep_metrics=deep_metrics,
            events=events,
        )

        phases = self._generate_match_phases(
            h_name=h_name,
            a_name=a_name,
            h_score=h_score,
            a_score=a_score,
            events=events,
            flab_h=flab_h,
            flab_a=flab_a,
        )

        match_context = None
        try:
            target_team_id = "FCT" if "FCT" in (h_id, a_id) else h_id
            match_context = self.context_calculator.calculate_context(
                match_id=m_id,
                team_id=target_team_id,
            )
        except Exception as e:
            logger.debug("Failed to calculate context for %s: %s", m_id, e)

        result: Dict[str, Any] = {
            "match_id": m_id,
            "home_formation": formations.get("home_initial", "4-4-2"),
            "away_formation": formations.get("away_initial", "4-4-2"),
            "tactical_highlights": highlights,
            "phases": phases,
            "deep_metrics": deep_metrics,
            "key_tactical_events": events,
        }
        if match_context:
            result["match_context"] = match_context

        return result

    # -------------------------------------------------------------------------
    # Core Synthesis: Base Style -> Match Plan -> Clash -> Discrepancy Evaluation
    # -------------------------------------------------------------------------

    def _synthesize_tactical_highlights(
        self,
        h_id: str,
        a_id: str,
        h_name: str,
        a_name: str,
        h_score: int,
        a_score: int,
        formations: Dict[str, str],
        flab_h: Dict[str, Any],
        flab_a: Dict[str, Any],
        deep_metrics: Dict[str, Any],
        events: List[Dict[str, Any]],
    ) -> List[str]:
        """Synthesize Layer 3 Grounded Explanations with Outcome Bias elimination."""
        highlights: List[str] = []

        h_prof = self.profiles.get(h_id, {})
        a_prof = self.profiles.get(a_id, {})

        h_form = formations.get("home_initial", "4-4-2")
        a_form = formations.get("away_initial", "4-4-2")

        # 1. Base Style & Matchday Intent
        h_base = self._get_base_style_summary(h_prof)
        a_base = self._get_base_style_summary(a_prof)
        h_plan = self._derive_matchday_plan(h_prof, flab_h, h_form)
        a_plan = self._derive_matchday_plan(a_prof, flab_a, a_form)

        highlights.append(
            f"【基本スタイルと今節の狙い】{h_name}（基本方針: {h_base}）は{h_form}の布陣を敷き、{h_plan}。対する{a_name}（基本方針: {a_base}）は{a_form}で迎え撃ち、{a_plan}。"
        )

        # 2. Pitch Clash & Tactical Performance (Tactical Process Evaluation)
        clash_text, tactical_winner = self._evaluate_tactical_clash(
            h_name=h_name,
            a_name=a_name,
            flab_h=flab_h,
            flab_a=flab_a,
            deep_metrics=deep_metrics,
        )
        highlights.append(f"【せめぎ合いの力学と内容評価】{clash_text}")

        # 3. Content vs Result Discrepancy (Elimination of Outcome Bias)
        discrepancy_text = self._evaluate_content_vs_result(
            h_name=h_name,
            a_name=a_name,
            h_score=h_score,
            a_score=a_score,
            tactical_winner=tactical_winner,
            flab_h=flab_h,
            flab_a=flab_a,
            deep_metrics=deep_metrics,
        )
        highlights.append(f"【内容と結果の因果・構造的総括】{discrepancy_text}")

        # 4. Decisive Goals Details
        goals = [e for e in events if self._is_true_goal(e)]
        if goals:
            goal_strs = []
            for g in goals[:4]:
                min_str = f"{g.get('minute', '-')}分"
                p_name = g.get("player_name") or "得点者"
                desc = g.get("description_text") or ""
                goal_strs.append(f"{min_str} {p_name} ({desc})")
            highlights.append(f"【試合を動かした得点】{ ' / '.join(goal_strs) }")

        return highlights

    def _get_base_style_summary(self, prof: Dict[str, Any]) -> str:
        """Extract high-level season philosophical identity."""
        in_pos = prof.get("in_possession", {})
        style = in_pos.get("build_up_style", "")
        if "positional" in style or "possession" in style:
            return "後方からの丁寧なビルドアップと位置的優位の追求"
        elif "vertical" in style or "counter" in style:
            return "ボール奪取からの素早い縦方向へのダイレクトアタック"
        elif "wide" in style or "wing" in style:
            return "両大外のウイング・SBを活用したサイドアタック"
        return in_pos.get("summary", "攻守のバランスと即時奪回")[:40].rstrip("。")

    def _derive_matchday_plan(
        self,
        prof: Dict[str, Any],
        flab: Dict[str, Any],
        form: str,
    ) -> str:
        """Analyze matchday execution and tactical adjustments."""
        mgr = prof.get("manager") or ""
        mgr_str = f"{mgr}監督のもと、" if mgr else ""

        poss = flab.get("possession_rate") or 50.0
        crosses = flab.get("crosses") or 0
        passes = flab.get("passes") or 0

        if poss >= 55.0 and passes >= 480:
            plan = "ボール保持率を高めて相手を自陣に押し込み、中央・ハーフスペースを崩すプラン"
        elif crosses >= 18:
            plan = "サイドへの配球を増やし、相手守備ブロックの外側からクロスを連打してPA内へ圧力をかけるプラン"
        elif poss < 44.0:
            plan = "あえて保持を相手に譲り、中央を固めたブロック守備から背後の広大なスペースを突くロングカウンタープラン"
        else:
            plan = "中盤のインテンシティを維持し、トランジションの速度で相手の隙を突くプラン"

        return f"{mgr_str}{plan}を選択"

    def _evaluate_tactical_clash(
        self,
        h_name: str,
        a_name: str,
        flab_h: Dict[str, Any],
        flab_a: Dict[str, Any],
        deep_metrics: Dict[str, Any],
    ) -> Tuple[str, str]:
        """
        Evaluate which team succeeded in executing their tactical process.
        Returns: (explanation_text, tactical_winner: 'HOME' | 'AWAY' | 'EQUAL')
        """
        ft = deep_metrics.get("field_tilt", {})
        conv = deep_metrics.get("conversion_rates", {})
        h_tilt = ft.get("home_field_tilt", 50.0)
        a_tilt = ft.get("away_field_tilt", 50.0)
        h_rate = conv.get("home", {}).get("rate_30_to_pa", 0.0)
        a_rate = conv.get("away", {}).get("rate_30_to_pa", 0.0)

        # Home team heavily dominated territory and penetrated
        if h_tilt >= 60.0 and h_rate >= 24.0:
            text = (
                f"{h_name}が敵陣支配率{h_tilt}%で相手を押し込み、PA進入率{h_rate}%と相手の守備ブロックを内側と外側の両面からこじ開けることに成功。"
                f"対する{a_name}はクリア後のボールを前線で収められず、自陣深くに釘付けにされ守勢を強いられた。"
            )
            return text, "HOME"

        # Home team dominated territory but got suffocated by away block (Away defensive success)
        elif h_tilt >= 60.0 and h_rate < 24.0:
            text = (
                f"{h_name}が敵陣支配率{h_tilt}%でボールを持たされたものの、{a_name}の中央密集ブロックに阻まれPA侵入率は{h_rate}%と外回りに終始。"
                f"戦術的な仕掛けのプロセスとしては、{a_name}の中央封鎖・シュートコース限定の防壁プランが完全に機能した。"
            )
            return text, "AWAY"

        # Away team heavily dominated territory and penetrated
        elif a_tilt >= 60.0 and a_rate >= 24.0:
            text = (
                f"アウェイの{a_name}が敵陣支配率{a_tilt}%と試合の主導権を掌握。PA進入率{a_rate}%と相手ブロックのスライドを破断して深くまで侵入。"
                f"{h_name}は自陣での消火活動に追われ、前線への効果的なカウンタールートを遮断された。"
            )
            return text, "AWAY"

        # Away team had territory but Home defended stoutly (Home defensive success)
        elif a_tilt >= 60.0 and a_rate < 24.0:
            text = (
                f"{a_name}が敵陣支配率{a_tilt}%で攻勢に出たものの、{h_name}がPA侵入率{a_rate}%に抑え込む鉄壁の中央ブロックを形成。"
                f"危険なバイタルエリアを徹底的に封鎖し、外に追いやる{h_name}の守備プランが奏功した。"
            )
            return text, "HOME"

        # Midfield balanced clash
        else:
            text = (
                f"敵陣支配率は{h_name} {h_tilt}% 対 {a_name} {a_tilt}%と互角のせめぎ合い。"
                f"互いに中盤でのセカンドボール回収とトランジションへの素早い切り替えを徹底し、決定的なバイタルエリアの進入を許さない一進一退の力学となった。"
            )
            return text, "EQUAL"

    def _evaluate_content_vs_result(
        self,
        h_name: str,
        a_name: str,
        h_score: int,
        a_score: int,
        tactical_winner: str,
        flab_h: Dict[str, Any],
        flab_a: Dict[str, Any],
        deep_metrics: Dict[str, Any],
    ) -> str:
        """
        Examine the discrepancy between tactical process success and final scoreline.
        Outcome Bias Buster: Winning does not always mean the plan was superior.
        """
        score_winner = "HOME" if h_score > a_score else ("AWAY" if a_score > h_score else "DRAW")
        h_on = flab_h.get("shots_on_target", 0)
        a_on = flab_a.get("shots_on_target", 0)

        # Case 1: Tactical Process aligned with Scoreline (Pure Execution Mastery)
        if tactical_winner == score_winner and score_winner != "DRAW":
            winner_name = h_name if score_winner == "HOME" else a_name
            loser_name = a_name if score_winner == "HOME" else h_name
            w_on = h_on if score_winner == "HOME" else a_on
            l_on = a_on if score_winner == "HOME" else h_on
            return (
                f"【内容と結果の一致】{winner_name}の戦術的狙いがピッチ上で完全に機能し、枠内シュート{w_on}本と決定機を確実にゴールへ結びつけて順当な勝利を収めた。"
                f"{loser_name}は内容・結果の両面で圧倒され、プランの修正が後手に回った。"
            )

        # Case 2: Process was successful, but Result was a Loss/Draw (Tactical Superiority vs Score Failure)
        elif tactical_winner != "EQUAL" and tactical_winner != score_winner and score_winner != "DRAW":
            proc_winner = h_name if tactical_winner == "HOME" else a_name
            score_win = h_name if score_winner == "HOME" else a_name
            p_on = h_on if tactical_winner == "HOME" else a_on
            s_on = h_on if score_winner == "HOME" else a_on
            return (
                f"【内容と結果の乖離（戦術的優位と決定力の逆転）】試合をデザインし狙い通りにピッチを支配したのは{proc_winner}だったが、最後の決定力不足や相手GKの好守に阻まれスコアに直結せず。"
                f"逆に{score_win}は戦術的には劣勢に立たされながらも、ワンチャンスの決定打やセットプレーを確実に仕留める勝負強さで結果（勝利）をもぎ取った。"
            )

        # Case 3: Dominant process held to a draw
        elif tactical_winner != "EQUAL" and score_winner == "DRAW":
            proc_winner = h_name if tactical_winner == "HOME" else a_name
            proc_loser = a_name if tactical_winner == "HOME" else h_name
            return (
                f"【内容と結果の乖離（仕掛けの優勢とスコアの膠着）】{proc_winner}が明確な戦術的イニシアチブを握り攻勢を強めたものの、{proc_loser}の粘り強い水際守備の前に1点が遠く{h_score}-{a_score}のドロー。"
                f"内容面で優勢だった{proc_winner}にとっては悔やまれる勝ち点1、耐え抜いた{proc_loser}にとっては戦術的規律がもたらした価値ある勝ち点1となった。"
            )

        # Case 4: Equal clash producing decisive win or draw
        else:
            if score_winner == "DRAW":
                return (
                    f"【拮抗した力学の結実】両チームのプランが互いのストロングポイントを打ち消し合い、戦術的な完成度と集中力が拮抗した必然の{h_score}-{a_score}。"
                )
            else:
                winner_name = h_name if score_winner == "HOME" else a_name
                return (
                    f"【微差が分けた結末】内容面では互角のせめぎ合いだったが、ペナルティエリア内での一瞬の隙やフィニッシュの個の精度で{winner_name}がわずかに上回り、激闘を制した。"
                )

    # -------------------------------------------------------------------------
    # Helper DB Queries & Phase Generation
    # -------------------------------------------------------------------------

    def _is_true_goal(self, e: Dict[str, Any]) -> bool:
        """Verify that an event is a genuine goal, not a missed shot or telemetry line."""
        if e.get("event_type") != "GOAL":
            return False
        desc = (e.get("description_text") or "").lower()
        negative_words = ["外れてしまう", "外れる", "セーブ", "ブロック", "ここまでのシュート", "期待値"]
        for neg in negative_words:
            if neg in desc:
                return False
        positive_words = ["得点", "ゴール", "ネットを揺らす", "決める", "goooooal", "先制", "追加点", "ダメ押し"]
        return any(pos in desc for pos in positive_words)

    def _fetch_flab_stats(
        self,
        conn: sqlite3.Connection,
        match_id: str,
        home_id: str,
        away_id: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Fetch Football LAB team match stats for home and away."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM team_match_flab_stats
            WHERE match_id = ?;
            """,
            (match_id,),
        )
        rows = cur.fetchall()
        flab_h: Dict[str, Any] = {}
        flab_a: Dict[str, Any] = {}
        for r in rows:
            if r.get("team_id") == home_id:
                flab_h = r
            elif r.get("team_id") == away_id:
                flab_a = r
        return flab_h, flab_a

    def _fetch_formations(
        self,
        conn: sqlite3.Connection,
        match_id: str,
        home_id: str,
        away_id: str,
    ) -> Dict[str, str]:
        """Fetch initial tactical formations for match."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT home_initial_formation, away_initial_formation
            FROM match_formations
            WHERE match_id = ?;
            """,
            (match_id,),
        )
        row = cur.fetchone()
        if row:
            return {
                "home_initial": row.get("home_initial_formation") or "4-4-2",
                "away_initial": row.get("away_initial_formation") or "4-4-2",
            }
        return {"home_initial": "4-4-2", "away_initial": "4-4-2"}

    def _fetch_events(
        self,
        conn: sqlite3.Connection,
        match_id: str,
    ) -> List[Dict[str, Any]]:
        """Fetch sorted match events and sanitize team abbreviations in descriptions."""
        cur = conn.cursor()
        cur.execute(
            """
            SELECT minute, period, team_id, player_name, event_type,
                   zone_name, xg, situation, description_text
            FROM match_events
            WHERE match_id = ?
            ORDER BY minute ASC;
            """,
            (match_id,),
        )
        raw_events = cur.fetchall()
        sanitized = []
        for e in raw_events:
            ev = dict(e)
            desc = ev.get("description_text") or ""
            for code, full_name in TEAM_NAME_MAP.items():
                if code in desc:
                    desc = desc.replace(code, full_name)
            ev["description_text"] = desc
            sanitized.append(ev)
        return sanitized

    def _calculate_deep_metrics(
        self,
        flab_h: Dict[str, Any],
        flab_a: Dict[str, Any],
        h_score: int,
        a_score: int,
    ) -> Dict[str, Any]:
        """Compute objective deep metrics (Field Tilt, conversion rates, intensity)."""
        h_m30 = flab_h.get("m30_entries") or 0
        a_m30 = flab_a.get("m30_entries") or 0
        tot_m30 = h_m30 + a_m30
        h_tilt = round((h_m30 / tot_m30 * 100), 1) if tot_m30 > 0 else 50.0
        a_tilt = round(100.0 - h_tilt, 1)

        h_pa = flab_h.get("pa_entries") or 0
        a_pa = flab_a.get("pa_entries") or 0
        h_conv = round((h_pa / h_m30 * 100), 1) if h_m30 > 0 else 0.0
        a_conv = round((a_pa / a_m30 * 100), 1) if a_m30 > 0 else 0.0

        h_dist = round((flab_h.get("distance_m") or 0) / 1000.0, 1)
        a_dist = round((flab_a.get("distance_m") or 0) / 1000.0, 1)
        h_spr = flab_h.get("sprints") or 0
        a_spr = flab_a.get("sprints") or 0

        return {
            "field_tilt": {
                "home_field_tilt": h_tilt,
                "away_field_tilt": a_tilt,
            },
            "conversion_rates": {
                "home": {
                    "m30_entries": h_m30,
                    "pa_entries": h_pa,
                    "rate_30_to_pa": h_conv,
                },
                "away": {
                    "m30_entries": a_m30,
                    "pa_entries": a_pa,
                    "rate_30_to_pa": a_conv,
                },
            },
            "intensity": {
                "home_distance_km": h_dist,
                "away_distance_km": a_dist,
                "home_sprints": h_spr,
                "away_sprints": a_spr,
            },
        }

    def _generate_match_phases(
        self,
        h_name: str,
        a_name: str,
        h_score: int,
        a_score: int,
        events: List[Dict[str, Any]],
        flab_h: Dict[str, Any],
        flab_a: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Generate match phases strictly mapped to actual minute events."""
        phase_ranges = [
            ("0-15", 0, 15),
            ("15-30", 16, 30),
            ("30-45+", 31, 50),
            ("46-60", 46, 60),
            ("60-75", 61, 75),
            ("75-90+", 76, 120),
        ]

        phases: List[Dict[str, Any]] = []

        for p_label, start_m, end_m in phase_ranges:
            p_events = [
                e for e in events
                if e.get("minute") is not None and start_m <= e["minute"] <= end_m
            ]
            goals_in_p = [e for e in p_events if self._is_true_goal(e)]
            cards_in_p = [e for e in p_events if e.get("event_type") in ("YELLOW_CARD", "RED_CARD")]

            if goals_in_p:
                h_goals = sum(1 for g in goals_in_p if g.get("team_id") == flab_h.get("team_id"))
                a_goals = sum(1 for g in goals_in_p if g.get("team_id") == flab_a.get("team_id"))
                if h_goals > a_goals:
                    dominant = "HOME"
                elif a_goals > h_goals:
                    dominant = "AWAY"
                else:
                    dominant = "EQUAL"
            else:
                dominant = "EQUAL"

            summary_sentences = []
            if goals_in_p:
                for g in goals_in_p:
                    scorer = g.get("player_name") or "選手"
                    m_min = g.get("minute", "-")
                    desc = g.get("description_text", "ゴール")
                    summary_sentences.append(f"【得点動意】{m_min}分、{scorer}がネットを揺らしスコアが動く（{desc}）。")
            else:
                if p_label == "0-15":
                    summary_sentences.append(f"立ち上がり。互いに守備陣形のコンパクトネスを保ちつつ、{h_name}と{a_name}が相手のプレス構造を探り合う。")
                elif p_label == "15-30":
                    summary_sentences.append(f"中盤でのポゼッション攻防。相手ブロックの外回しを強いられる時間帯があり、バイタルへの縦パスコースをうかがう。")
                elif p_label == "30-45+":
                    summary_sentences.append(f"前半終盤。セットプレーやサイドからのクロスを起点にゴール前での進入圧力が高まる。")
                elif p_label == "46-60":
                    summary_sentences.append(f"後半立ち上がり。ハーフタイムの指示を受けてプレスのギアを入れ直し、トランジションのスピードを上げる。")
                elif p_label == "60-75":
                    summary_sentences.append(f"選手交代による陣形や運動量のテコ入れ。相手の疲労で生じたライン間のスペースを突き合う攻防。")
                elif p_label == "75-90+":
                    summary_sentences.append(f"試合の最終局面。スコア状況に応じたリスク管理と、前線へのロングフィードを交えた攻防。")

            if cards_in_p:
                card_strs = [f"{c.get('minute')}分 {c.get('player_name')}警告" for c in cards_in_p]
                summary_sentences.append(f"警告・規律: {', '.join(card_strs)}。")

            phases.append({
                "phase": p_label,
                "dominant_team": dominant,
                "momentum_summary": " ".join(summary_sentences),
                "pressing_battle": f"{h_name}のブロック守備と{a_name}の前進ルートの駆け引き。",
                "tactical_adjustments": "局面に応じたラインコントロールとサポート距離の調整。",
            })

        return phases
