# -*- coding: utf-8 -*-
"""
Review Curation Service (pipeline/review_curation_service.py).
Fully updated to conform to Layer 2 metrics analysis & hypothesis generation.
Extracts deep match facts, analyzes event dynamics using Layer 2 metrics,
formulates grounded tactical hypotheses, and compiles curated review reports.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from scripts.calculate_match_context import MatchContextCalculator

logger = logging.getLogger("review_curation_service")


class ReviewCurationService:
    """Service to extract Layer 2 match facts, analyze match dynamics, and compile curated reviews."""

    def __init__(
        self,
        db_path: Optional[str] = None,
    ) -> None:
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.context_calculator = MatchContextCalculator(db_path=self.db_path)

    def extract_match_review_facts(
        self,
        match_id: str,
    ) -> Dict[str, Any]:
        """Extract comprehensive Layer 1 & Layer 2 facts from SQLite and tactical context."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # 1. Basic Match info
        cursor.execute(
            """
            SELECT match_id, season, matchweek, date, home_team_id, away_team_id,
                   home_score, away_score, stadium, weather, pitch_condition,
                   attendance, source_updated_stage
            FROM matches
            WHERE match_id = ?
            """,
            (match_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Match not found for match_id: {match_id}")

        basic_info: Dict[str, Any] = {
            "match_id": row[0],
            "season": row[1],
            "matchweek": row[2],
            "date": row[3],
            "home_team_id": row[4],
            "away_team_id": row[5],
            "home_score": row[6] if row[6] is not None else 0,
            "away_score": row[7] if row[7] is not None else 0,
            "stadium": row[8] or "未定",
            "weather": row[9] or "不明",
            "pitch_condition": row[10] or "良好",
            "attendance": row[11] or 0,
            "stage": row[12] or 1,
        }

        # 2. Team match stats (Layer 1 & Layer 2 intensity)
        cursor.execute(
            """
            SELECT team_id, possession, xg, shots, shots_on_target,
                   total_distance_km, sprints
            FROM team_match_stats
            WHERE match_id = ? AND (period = 'ALL' OR period = 'FULL')
            """,
            (match_id,),
        )
        team_stats_rows = cursor.fetchall()
        team_stats: Dict[str, Dict[str, Any]] = {}
        for ts in team_stats_rows:
            team_stats[ts[0]] = {
                "possession": ts[1] if ts[1] is not None else 50.0,
                "xg": ts[2] if ts[2] is not None else 0.0,
                "shots": ts[3] if ts[3] is not None else 0,
                "shots_on_target": ts[4] if ts[4] is not None else 0,
                "distance_km": ts[5] if ts[5] is not None else 0.0,
                "sprints": ts[6] if ts[6] is not None else 0,
            }

        # 3. Match events (goals, substitutions, cards, turning points)
        cursor.execute(
            """
            SELECT minute, period, event_type, team_id, player_name, description_text
            FROM match_events
            WHERE match_id = ?
            ORDER BY minute ASC, event_id ASC
            """,
            (match_id,),
        )
        event_rows = cursor.fetchall()
        events: List[Dict[str, Any]] = []
        for ev in event_rows:
            events.append(
                {
                    "minute": ev[0],
                    "period": ev[1],
                    "type": ev[2],
                    "team_id": ev[3],
                    "player_name": ev[4],
                    "description": ev[5],
                },
            )

        # 4. Detailed player stats with Layer 2 metrics (CBP, duels, touches, distance)
        cursor.execute(
            """
            SELECT player_name, team_id, position, number, is_starter, minutes_played,
                   goals, assists, xg, xa, touches, duels_won, distance_km, cbp_points
            FROM player_match_stats
            WHERE match_id = ?
            ORDER BY cbp_points DESC, goals DESC, assists DESC
            """,
            (match_id,),
        )
        player_rows = cursor.fetchall()
        players: List[Dict[str, Any]] = []
        for pr in player_rows:
            players.append(
                {
                    "name": pr[0],
                    "team_id": pr[1],
                    "position": pr[2] or "-",
                    "number": pr[3] or 0,
                    "is_starter": bool(pr[4]),
                    "minutes_played": pr[5] or 0,
                    "goals": pr[6] or 0,
                    "assists": pr[7] or 0,
                    "xg": pr[8] or 0.0,
                    "xa": pr[9] or 0.0,
                    "touches": pr[10] or 0,
                    "duels_won": pr[11] or 0,
                    "distance_km": pr[12] or 0.0,
                    "cbp": pr[13] or 0.0,
                },
            )

        conn.close()

        # 5. Extract match context (Schedule, fatigue, disciplinary, weather)
        home_id = basic_info["home_team_id"]
        away_id = basic_info["away_team_id"]
        try:
            home_ctx = self.context_calculator.calculate_context(match_id=match_id, team_id=home_id)
        except Exception:
            home_ctx = {}

        try:
            away_ctx = self.context_calculator.calculate_context(match_id=match_id, team_id=away_id)
        except Exception:
            away_ctx = {}

        # 6. Structured tactical data if available
        tactical_json_path = ROOT_DIR / "data" / "structured" / f"{match_id}_tactical.json"
        tactical_data: Dict[str, Any] = {}
        if tactical_json_path.exists():
            try:
                tactical_data = json.loads(tactical_json_path.read_text(encoding="utf-8"))
            except Exception:
                tactical_data = {}

        return {
            "basic_info": basic_info,
            "team_stats": team_stats,
            "events": events,
            "players": players,
            "notable_players": players,
            "home_context": home_ctx,
            "away_context": away_ctx,
            "tactical_data": tactical_data,
        }

    def analyze_layer2_dynamics_and_hypotheses(
        self,
        facts: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Synthesize Layer 2 metrics to derive structured tactical events and hypotheses.
        Evaluates physical intensity discrepancy, transition efficiency, and turning points.
        """
        basic = facts.get("basic_info", {})
        team_stats = facts.get("team_stats", {})
        players = facts.get("players", [])
        events = facts.get("events", [])
        home_id = basic.get("home_team_id", "HOME")
        away_id = basic.get("away_team_id", "AWAY")
        home_score = basic.get("home_score", 0)
        away_score = basic.get("away_score", 0)

        home_st = team_stats.get(home_id, {})
        away_st = team_stats.get(away_id, {})

        # Intensity comparison
        h_dist = home_st.get("distance_km", 0.0)
        a_dist = away_st.get("distance_km", 0.0)
        h_spr = home_st.get("sprints", 0)
        a_spr = away_st.get("sprints", 0)
        h_xg = home_st.get("xg", 0.0)
        a_xg = away_st.get("xg", 0.0)

        # Top performers by CBP
        home_players = [p for p in players if p["team_id"] == home_id]
        away_players = [p for p in players if p["team_id"] == away_id]

        top_home_cbp = sorted(home_players, key=lambda x: x["cbp"], reverse=True)[:3]
        top_away_cbp = sorted(away_players, key=lambda x: x["cbp"], reverse=True)[:3]

        # Goals events
        goals = [e for e in events if e.get("type") == "GOAL"]

        # Derive hypotheses
        hypotheses: List[Dict[str, str]] = []

        # Hypothesis 1: Intensity and Transition Dynamics
        if a_spr > h_spr + 5 or a_dist > h_dist + 2.0:
            spr_diff = a_spr - h_spr
            hypotheses.append(
                {
                    "title": "インテンシティ格差とトランジションの制圧",
                    "fact": f"{away_id}のスプリント数（{a_spr}回）が{home_id}（{h_spr}回）を{spr_diff}回上回り、走行距離でも{a_dist:.1f}km vs {h_dist:.1f}kmと優勢。",
                    "hypothesis": f"【推測】ボール非保持時・即時奪回時におけるスプリント回数の優位性が、{home_id}のパスコースを限定させ、速攻への導線を完全に遮断した。",
                },
            )
        elif h_spr > a_spr + 5 or h_dist > a_dist + 2.0:
            spr_diff = h_spr - a_spr
            hypotheses.append(
                {
                    "title": "ハイプレス運動量とピッチ支配力",
                    "fact": f"{home_id}のスプリント数（{h_spr}回）が{away_id}（{a_spr}回）を上回り、走行距離でも圧倒。",
                    "hypothesis": f"【推測】ホームの利を活かした高い運動量が相手陣でのボール回収確率を引き上げ、主導権掌握に直結した。",
                },
            )

        # Hypothesis 2: Central Hub and Tactical Linkage (CBP & Touches)
        if top_away_cbp and top_away_cbp[0]["cbp"] >= 10.0:
            hub = top_away_cbp[0]
            hypotheses.append(
                {
                    "title": f"中盤の戦術的ハブ機能（{hub['name']}の圧倒的関与）",
                    "fact": f"{hub['name']}がCBP {hub['cbp']:.1f}ポイント・タッチ数 {hub['touches']}回・デュエル勝利 {hub['duels_won']}回を記録。",
                    "hypothesis": f"【推測】{hub['name']}が相手のファーストプレッシャーの背後でボールを引き出し、左右への配球と縦パスの出し手として相手守備網を広げる決定打となった。",
                },
            )
        elif top_home_cbp and top_home_cbp[0]["cbp"] >= 10.0:
            hub = top_home_cbp[0]
            hypotheses.append(
                {
                    "title": f"攻守の軸としての躍動（{hub['name']}）",
                    "fact": f"{hub['name']}がCBP {hub['cbp']:.1f}ポイントを記録し、ゲームメイクの中心として機能。",
                    "hypothesis": f"【推測】中盤底でのボール保持安定と前線への配給テンポをコントロールした。",
                },
            )

        # Hypothesis 3: Finishing Efficiency vs Chance Creation (xG vs Actual Goals)
        if away_score >= 3:
            hypotheses.append(
                {
                    "title": "決定機の質と決定力の構造的連動",
                    "fact": f"{away_id}はシュート{away_st.get('shots', 0)}本中{away_st.get('shots_on_target', 0)}本が枠内。xG {a_xg:.2f}に対し{away_score}得点を記録。",
                    "hypothesis": f"【推測】ペナルティエリア内でのラストパス・ラストアクションの質が高く、GKとの1対1や高確率ゾーンからのシュートを冷静に完結させた。",
                },
            )
        elif home_score >= 3:
            hypotheses.append(
                {
                    "title": "枠内シュート精度と決定力爆発",
                    "fact": f"{home_id}はシュート{home_st.get('shots', 0)}本から{home_score}得点を奪取。",
                    "hypothesis": f"【推測】相手の守備ブロックが崩れた瞬間を的確に見逃さず、高精度フィニッシュで仕留めた。",
                },
            )

        return {
            "top_home_cbp": top_home_cbp,
            "top_away_cbp": top_away_cbp,
            "goals": goals,
            "hypotheses": hypotheses,
        }

    def generate_curation_workspace(
        self,
        match_id: str,
    ) -> Dict[str, Any]:
        """Extract facts and generate deterministic review decision branches grounded in Layer 2."""
        facts = self.extract_match_review_facts(match_id)
        dynamics = self.analyze_layer2_dynamics_and_hypotheses(facts)
        branches = self._build_review_branches(facts, dynamics)
        return {
            "facts": facts,
            "dynamics": dynamics,
            "branches": branches,
        }

    def _build_review_branches(
        self,
        facts: Dict[str, Any],
        dynamics: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Construct deterministic decision branches for post-match tactical review."""
        basic = facts.get("basic_info", {})
        home_id = basic.get("home_team_id", "HOME")
        away_id = basic.get("away_team_id", "AWAY")
        home_score = basic.get("home_score", 0)
        away_score = basic.get("away_score", 0)
        team_stats = facts.get("team_stats", {})

        branches: List[Dict[str, Any]] = [
            self._create_deciding_factor_branch(
                home_id=home_id,
                away_id=away_id,
                home_score=home_score,
                away_score=away_score,
                team_stats=team_stats,
                dynamics=dynamics,
            ),
            self._create_tactical_matchup_branch(
                home_id=home_id,
                away_id=away_id,
                facts=facts,
                dynamics=dynamics,
            ),
            self._create_impact_player_branch(
                facts=facts,
                dynamics=dynamics,
            ),
        ]
        return branches

    def _create_deciding_factor_branch(
        self,
        home_id: str,
        away_id: str,
        home_score: int,
        away_score: int,
        team_stats: Dict[str, Any],
        dynamics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate branch options for the game deciding turning point."""
        home_st = team_stats.get(home_id, {})
        away_st = team_stats.get(away_id, {})
        home_shots = home_st.get("shots", 0)
        away_shots = away_st.get("shots", 0)
        winner_id = away_id if away_score > home_score else (home_id if home_score > away_score else None)

        if winner_id:
            result_context = f"{winner_id} が {max(home_score, away_score)}-{min(home_score, away_score)} で勝利。"
        else:
            result_context = f"{home_score}-{away_score} の引き分け。"

        return {
            "branch_id": "deciding_factor",
            "title": "【勝敗の決定打・ターニングポイント】試合の趨勢を分けた要因",
            "category": "turning_point",
            "options": [
                {
                    "option_id": "A",
                    "label": "ハイインテンシティと即時奪回によるショートカウンターの炸裂",
                    "fact_basis": f"【事実】シュート数 {home_id} {home_shots}本 vs {away_id} {away_shots}本。スプリント数・走行距離での優位性を保持しての複数得点（{result_context}）。",
                    "inference": "【推測】ボールロスト直後のトランジション速度が相手陣形のスライドを上回り、守備ブロックの再構築前に決定機を創出した。",
                },
                {
                    "option_id": "B",
                    "label": "サイドのスペース攻略とDFライン背後への配球クオリティ",
                    "fact_basis": f"【事実】ペナルティエリア進入回数および高精度クロス・ロングフィードからの決定機創出。",
                    "inference": "【推測】相手のコンパクトな中央ブロックに対し、外から揺さぶり背後のスペースを突く攻撃設計が機能した。",
                },
                {
                    "option_id": "C",
                    "label": "セットプレーおよびセカンドボール回収の徹底",
                    "fact_basis": "【事実】中盤のこぼれ球奪取率とペナルティエリア外からのセカンドチャンスにおけるシュート発生。",
                    "inference": "【推測】ルーズボールの予測とデュエルでの粘りが主導権を手放さないゲームクローズに寄与した。",
                },
            ],
        }

    def _create_tactical_matchup_branch(
        self,
        home_id: str,
        away_id: str,
        facts: Dict[str, Any],
        dynamics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate branch options for tactical matchup evaluation."""
        return {
            "branch_id": "tactical_evaluation",
            "title": "【戦術的噛み合わせの総括】ピッチ上の主導権争いと構造的力学",
            "category": "tactical_matchup",
            "options": [
                {
                    "option_id": "A",
                    "label": "ハイプレス回避とブロック間ポケットの有効活用",
                    "fact_basis": "【事実】中盤ボランチ・トップ下を中心としたボール経由数と相手プレッシャーライン背後への前進パス。",
                    "inference": "【推測】相手の前プレを誘引して空いた中間ポジションにボールを差し込み、中央突破の足がかりを作った。",
                },
                {
                    "option_id": "B",
                    "label": "5バック気味の強固な撤退守備 vs ポゼッションによる崩し",
                    "fact_basis": "【事実】ボール保持率の偏りと自陣深くでのシュートブロック・クリア数。",
                    "inference": "【推測】相手のカウンター警戒ラインを保ちつつ、リスクを最小限に抑えたボール循環でスペースの創出を試みた。",
                },
                {
                    "option_id": "C",
                    "label": "プレッシャー強度の時間帯別推移と交代策による打開",
                    "fact_basis": "【事実】後半60分以降の交代出場選手のシュート関与・アシスト記録。",
                    "inference": "【推測】疲労が見え始めた相手守備陣に対しフレッシュなアタッカーを投入し、スピードで圧倒した。",
                },
            ],
        }

    def _create_impact_player_branch(
        self,
        facts: Dict[str, Any],
        dynamics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate branch options for player evaluation."""
        players = facts.get("players", [])
        top_cbp_p = players[0] if players else {"name": "中心選手", "team_id": "TEAM", "cbp": 0.0}
        second_cbp_p = players[1] if len(players) > 1 else {"name": "キーマン", "team_id": "TEAM", "cbp": 0.0}

        return {
            "branch_id": "impact_player",
            "title": "【殊勲選手・キーマン評価】ピッチで最も輝いた貢献",
            "category": "player_evaluation",
            "options": [
                {
                    "option_id": "A",
                    "label": f"ピッチを支配した最高評価選手（{top_cbp_p['name']}）",
                    "fact_basis": f"【事実】CBP {top_cbp_p.get('cbp', 0.0):.1f}pt、タッチ数 {top_cbp_p.get('touches', 0)}回、攻守に圧倒的な関与度を記録。",
                    "inference": "【推測】攻守の切り替えとゲームメイクの心臓部として機能し、チームの勝利に最も決定的な役割を果たした。",
                },
                {
                    "option_id": "B",
                    "label": f"戦術的タスクを完遂した影の立役者（{second_cbp_p['name']}）",
                    "fact_basis": f"【事実】CBP {second_cbp_p.get('cbp', 0.0):.1f}pt、デュエル・守備ブロックでの高い貢献度。",
                    "inference": "【推測】目立たない局面でも献身的なカバーリングとリスク管理を徹底し、全体の守備破綻を未然に防いだ。",
                },
            ],
        }

    def format_review_markdown(self, facts: Dict[str, Any]) -> str:
        """Render comprehensive review facts with Layer 2 metrics and hypotheses into clean Markdown."""
        basic = facts.get("basic_info", {})
        team_stats = facts.get("team_stats", {})
        events = facts.get("events", [])
        players = facts.get("players", [])
        home_ctx = facts.get("home_context", {})
        away_ctx = facts.get("away_context", {})

        home_id = basic.get("home_team_id", "HOME")
        away_id = basic.get("away_team_id", "AWAY")
        home_score = basic.get("home_score", 0)
        away_score = basic.get("away_score", 0)

        home_st = team_stats.get(home_id, {})
        away_st = team_stats.get(away_id, {})

        def _fmt(val: Any) -> str:
            if val is None:
                return "-"
            if isinstance(val, float):
                return f"{val:.1f}"
            return str(val)

        lines: List[str] = [
            f"# ⚽ 試合総括レポート: {basic.get('date', '')} {home_id} vs {away_id}",
            "",
            "## 1. 試合基本情報＆前提コンテキスト",
            f"- **スコア**: {home_id} {home_score} - {away_score} {away_id}",
            f"- **日程・会場**: {basic.get('date', '')} / {basic.get('stadium', '')}（天候: {basic.get('weather', '')} / 観客数: {basic.get('attendance', 0):,}人）",
        ]

        # Context details
        h_sched = home_ctx.get("schedule_fatigue", {})
        a_sched = away_ctx.get("schedule_fatigue", {})
        lines.extend(
            [
                f"- **日程・疲労度**: {home_id}（{h_sched.get('rest_days_display', '-')} / 疲労度: {h_sched.get('fatigue_risk_level', '-')}） vs {away_id}（{a_sched.get('rest_days_display', '-')} / 疲労度: {a_sched.get('fatigue_risk_level', '-')}）",
                "",
                "## 2. 確定スタッツ＆Layer2インテンシティ比較",
                f"| 指標 | {home_id} | {away_id} | 戦術的含意 |",
                "|---|---|---|---|",
                f"| スコア | {home_score} | {away_score} | 最終結果 |",
                f"| ボール支配率 (%) | {_fmt(home_st.get('possession'))} | {_fmt(away_st.get('possession'))} | ポゼッション主導権 |",
                f"| シュート数 | {_fmt(home_st.get('shots'))} | {_fmt(away_st.get('shots'))} | フィニッシュ創出頻度 |",
                f"| 枠内シュート | {_fmt(home_st.get('shots_on_target'))} | {_fmt(away_st.get('shots_on_target'))} | フィニッシュ精度 |",
                f"| 期待ゴール (xG) | {_fmt(home_st.get('xg'))} | {_fmt(away_st.get('xg'))} | 決定機の質的総量 |",
                f"| 総走行距離 (km) | {_fmt(home_st.get('distance_km'))} | {_fmt(away_st.get('distance_km'))} | チーム総運動量 |",
                f"| スプリント回数 | {_fmt(home_st.get('sprints'))} | {_fmt(away_st.get('sprints'))} | ハイインテンシティ頻度 |",
                "",
                "## 3. 主要マッチイベント＆時間帯別力学",
            ]
        )

        if events:
            for ev in events:
                minute = ev.get("minute", "-")
                ev_type = ev.get("type", "EVENT")
                desc = ev.get("description", "")
                pname = ev.get("player_name", "")
                tid = ev.get("team_id", "")
                icon = "⚽" if ev_type == "GOAL" else ("🔄" if ev_type == "SUBSTITUTION" else "🟨")
                lines.append(f"- **{minute}'** {icon} [{ev_type}] **{tid} {pname}**: {desc}".strip())
        else:
            lines.append("- イベント記録なし")

        lines.extend(
            [
                "",
                "## 4. 個人詳細スタッツ＆CBPトップパフォーマンス",
            ]
        )

        if players:
            lines.append(f"### 【{away_id}】トップパフォーマンス選手")
            for p in [x for x in players if x["team_id"] == away_id][:5]:
                lines.append(
                    f"- **#{p['number']} {p['name']}** ({p['position']}): "
                    f"CBP **{p['cbp']:.1f}pt**, 得点 {p['goals']}, アシスト {p['assists']}, "
                    f"タッチ {p['touches']}回, デュエル勝利 {p['duels_won']}回, 走破 {p['distance_km']:.1f}km",
                )
            lines.append("")
            lines.append(f"### 【{home_id}】トップパフォーマンス選手")
            for p in [x for x in players if x["team_id"] == home_id][:5]:
                lines.append(
                    f"- **#{p['number']} {p['name']}** ({p['position']}): "
                    f"CBP **{p['cbp']:.1f}pt**, 得点 {p['goals']}, アシスト {p['assists']}, "
                    f"タッチ {p['touches']}回, デュエル勝利 {p['duels_won']}回, 走破 {p['distance_km']:.1f}km",
                )
        else:
            lines.append("- 特筆スタッツ選手なし")

        # Section 5: Layer 2 Derived Hypotheses
        dynamics = self.analyze_layer2_dynamics_and_hypotheses(facts)
        hypotheses = dynamics.get("hypotheses", [])
        lines.extend(
            [
                "",
                "## 5. 🧠 Layer 2指標に基づく事象分析＆導き出される戦術的仮説",
                "> [!IMPORTANT]",
                "> 単なる結果論（Outcome Bias）を排除し、走行距離・スプリント・CBP・xGといったLayer 2客観スタッツから、試合の因果関係と戦術的メカニズムを紐解きます。",
                "",
            ]
        )

        if hypotheses:
            for i, hyp in enumerate(hypotheses, 1):
                lines.extend(
                    [
                        f"### ◆ 仮説{i}: {hyp['title']}",
                        f"- {hyp['fact']}",
                        f"- {hyp['hypothesis']}",
                        "",
                    ]
                )
        else:
            lines.append("- 算出された戦術仮説なし")

        return "\n".join(lines)

    def compile_curated_report(
        self,
        facts: Dict[str, Any],
        selections: Dict[str, str],
        custom_insights: Optional[str] = None,
    ) -> str:
        """Compile curated review Markdown integrating deterministic facts and selected branches."""
        base_md = self.format_review_markdown(facts)

        curated_lines = [
            "",
            "---",
            "## 🎯 共同キュレーション総括セクション（Curated Tactical Review）",
            "",
            "> [!NOTE]",
            "> 本セクションは確定事実スタッツに基づき、対話を通じて合意・採択された戦術的総括です。",
            "> 【事実】と【推測】は明確に分離して記録されています。",
            "",
        ]

        for title, choice_text in selections.items():
            curated_lines.append(f"### ◆ {title}")
            curated_lines.append(f"{choice_text}")
            curated_lines.append("")

        if custom_insights:
            curated_lines.extend(
                [
                    "### 💡 アナリスト・共同作成メモ",
                    custom_insights.strip(),
                    "",
                ]
            )

        return base_md + "\n" + "\n".join(curated_lines)

    def save_curated_report(
        self,
        output_path: Path,
        content: str,
    ) -> None:
        """Safely write curated report to target output path."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
