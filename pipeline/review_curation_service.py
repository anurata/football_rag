# -*- coding: utf-8 -*-
"""
Review Curation Service (pipeline/review_curation_service.py).
Supports collaborative post-match review and tactical summary authoring
by extracting objective post-match facts, generating decision branches
with strict Fact/Inference separation, and compiling curated review reports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import sqlite3

from pipeline.db import DEFAULT_DB_PATH, get_db_connection

ROOT_DIR = Path(__file__).resolve().parent.parent


class ReviewCurationService:
    """Service to extract match facts, generate review branches, and compile curated reviews."""

    def __init__(
        self,
        db_path: Optional[str] = None,
    ) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    def extract_match_review_facts(
        self,
        match_id: str,
    ) -> Dict[str, Any]:
        """Extract objective facts from SQLite and structured tactical files for a finished match."""
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

        # 2. Team match stats
        cursor.execute(
            """
            SELECT team_id, possession, xg, shots, shots_on_target,
                   total_distance_km, sprints
            FROM team_match_stats
            WHERE match_id = ? AND period = 'ALL'
            """,
            (match_id,),
        )
        team_stats_rows = cursor.fetchall()
        team_stats: Dict[str, Dict[str, Any]] = {}
        for ts in team_stats_rows:
            team_stats[ts[0]] = {
                "possession": ts[1],
                "xg": ts[2],
                "shots": ts[3],
                "shots_on_target": ts[4],
                "distance_km": ts[5],
                "sprints": ts[6],
            }

        # 3. Match events (goals, substitutions, cards)
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

        # 4. Top player stats (goals, assists, top distance)
        cursor.execute(
            """
            SELECT player_name, team_id, goals, assists, xg, xa, touches
            FROM player_match_stats
            WHERE match_id = ?
            ORDER BY goals DESC, assists DESC, touches DESC
            LIMIT 10
            """,
            (match_id,),
        )
        player_rows = cursor.fetchall()
        notable_players: List[Dict[str, Any]] = []
        for pr in player_rows:
            notable_players.append(
                {
                    "name": pr[0],
                    "team_id": pr[1],
                    "goals": pr[2] or 0,
                    "assists": pr[3] or 0,
                    "xg": pr[4] or 0.0,
                    "xa": pr[5] or 0.0,
                    "touches": pr[6] or 0,
                },
            )

        conn.close()

        # 5. Optional structured tactical json
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
            "notable_players": notable_players,
            "tactical_data": tactical_data,
        }

    def generate_curation_workspace(
        self,
        match_id: str,
    ) -> Dict[str, Any]:
        """Extract facts and generate deterministic review decision branches."""
        facts = self.extract_match_review_facts(match_id)
        branches = self._build_review_branches(facts)
        return {
            "facts": facts,
            "branches": branches,
        }

    def _build_review_branches(self, facts: Dict[str, Any]) -> List[Dict[str, Any]]:
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
            ),
            self._create_tactical_matchup_branch(
                home_id=home_id,
                away_id=away_id,
                facts=facts,
            ),
            self._create_impact_player_branch(
                facts=facts,
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
    ) -> Dict[str, Any]:
        """Generate branch options for the game deciding turning point."""
        home_st = team_stats.get(home_id, {})
        away_st = team_stats.get(away_id, {})
        home_shots = home_st.get("shots", 0)
        away_shots = away_st.get("shots", 0)

        if home_score > away_score:
            result_context = f"{home_id} が {home_score}-{away_score} で勝利。"
        elif away_score > home_score:
            result_context = f"{away_id} が {away_score}-{home_score} で勝利。"
        else:
            result_context = f"{home_score}-{away_score} の引き分け。"

        return {
            "branch_id": "deciding_factor",
            "title": "【勝敗の決定打・ターニングポイント】試合の趨勢を分けた要因",
            "category": "turning_point",
            "options": [
                {
                    "option_id": "A",
                    "label": "決定力と決定機創出のクオリティ差",
                    "fact_basis": f"【事実】最終スコア {home_score}-{away_score}（シュート数: {home_id} {home_shots}本 vs {away_id} {away_shots}本）。{result_context}",
                    "inference": "【推測】限られたチャンスにおけるフィニッシュ精度およびペナルティエリア内の落ち着きが勝敗に直結した。",
                },
                {
                    "option_id": "B",
                    "label": "守備ブロックの組織的強度とピンチでの粘り",
                    "fact_basis": f"【事実】相手の枠内シュートや攻撃圧力に対し、失点を最小限に抑え込んだスタッツ推移。",
                    "inference": "【推測】自陣ゴール前でのタイトなスライドと連動したブロック守備が相手の追加点・反撃の芽を摘んだ。",
                },
                {
                    "option_id": "C",
                    "label": "後半の選手交代・時間帯マネジメントの差",
                    "fact_basis": "【事実】後半の選手交代以降におけるボール保持率・シュート発生頻度の変化。",
                    "inference": "【推測】ベンチワークによるインテンシティの再注入またはゲームクローズ戦術の徹底が勝点配分を確定づけた。",
                },
            ],
        }

    def _create_tactical_matchup_branch(
        self,
        home_id: str,
        away_id: str,
        facts: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate branch options for tactical matchup evaluation."""
        return {
            "branch_id": "tactical_evaluation",
            "title": "【戦術的噛み合わせの総括】ピッチ上の主導権争い",
            "category": "tactical_matchup",
            "options": [
                {
                    "option_id": "A",
                    "label": "ハイプレスとビルドアップのせめぎ合い",
                    "fact_basis": f"【事実】敵陣でのボール奪取、プレッシングの強度、および後方からのパス成功率。",
                    "inference": f"【推測】プレッシャーを回避して前進できた時間帯に明確な優位性が現れていた。",
                },
                {
                    "option_id": "B",
                    "label": "サイドの局地戦（ウイング/SB vs WB/サイドCB）の攻防",
                    "fact_basis": "【事実】サイド攻撃比率とクロス配給数、サイドでのデュエル発生状況。",
                    "inference": "【推測】幅を使ったアタックとオーバーラップに対する守備対応が全体の守備陣形を広げた。",
                },
                {
                    "option_id": "C",
                    "label": "中盤のセカンドボール回収とトランジションのスピード",
                    "fact_basis": "【事実】ボランチを中心とした中盤のボール奪取数および攻守切り替え直後の前進スピード。",
                    "inference": "【推測】トランジションで素早く縦に付けられた側が相手ディフェンスの帰陣前に決定機を創出した。",
                },
            ],
        }

    def _create_impact_player_branch(
        self,
        facts: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate branch options for player evaluation."""
        notable = facts.get("notable_players", [])
        top_name = notable[0]["name"] if notable else "中心選手"
        second_name = notable[1]["name"] if len(notable) > 1 else "守備リーダー"

        return {
            "branch_id": "impact_player",
            "title": "【殊勲選手・キーマン評価】ピッチで最も輝いた貢献",
            "category": "player_evaluation",
            "options": [
                {
                    "option_id": "A",
                    "label": f"攻撃を牽引したキーマンの躍動（{top_name}）",
                    "fact_basis": f"【事実】得点・アシスト関与またはペナルティエリア付近での高いタッチ数・決定機関与（{top_name} 等）。",
                    "inference": "【推測】相手のマークを引き付けつつ自ら決定的な仕事を果たし、攻撃の起点となった。",
                },
                {
                    "option_id": "B",
                    "label": f"守備の要として破綻を防いだ貢献（{second_name}）",
                    "fact_basis": f"【事実】重要なシュートブロック、デュエル、ボール回収スタッツでの貢献（{second_name} 等）。",
                    "inference": "【推測】相手の決定的なアタックを寸前で食い止め、チーム全体のゲームコントロールを支えた。",
                },
            ],
        }

    def format_review_markdown(self, facts: Dict[str, Any]) -> str:
        """Render deterministic review facts into clean Markdown format."""
        basic = facts.get("basic_info", {})
        team_stats = facts.get("team_stats", {})
        events = facts.get("events", [])
        notable = facts.get("notable_players", [])

        home_id = basic.get("home_team_id", "HOME")
        away_id = basic.get("away_team_id", "AWAY")
        home_score = basic.get("home_score", 0)
        away_score = basic.get("away_score", 0)

        lines: List[str] = [
            f"# ⚽ 試合総括レポート: {basic.get('date', '')} {home_id} vs {away_id}",
            "",
            "## 1. 試合基本情報",
            f"- **スコア**: {home_id} {home_score} - {away_score} {away_id}",
            f"- **日程・会場**: {basic.get('date', '')} / {basic.get('stadium', '')}（天候: {basic.get('weather', '')} / 観客数: {basic.get('attendance', 0):,}人）",
            f"- **更新ステージ**: Stage {basic.get('stage', 1)}",
            "",
            "## 2. チーム確定スタッツ",
            f"| 指標 | {home_id} | {away_id} |",
            "|---|---|---|",
        ]

        home_st = team_stats.get(home_id, {})
        away_st = team_stats.get(away_id, {})

        def _fmt(val: Any) -> str:
            if val is None:
                return "-"
            if isinstance(val, float):
                return f"{val:.1f}"
            return str(val)

        lines.extend(
            [
                f"| スコア | {home_score} | {away_score} |",
                f"| シュート数 | {_fmt(home_st.get('shots'))} | {_fmt(away_st.get('shots'))} |",
                f"| 枠内シュート | {_fmt(home_st.get('shots_on_target'))} | {_fmt(away_st.get('shots_on_target'))} |",
                f"| ボール支配率 (%) | {_fmt(home_st.get('possession'))} | {_fmt(away_st.get('possession'))} |",
                f"| 期待ゴール (xG) | {_fmt(home_st.get('xg'))} | {_fmt(away_st.get('xg'))} |",
                f"| 走行距離 (km) | {_fmt(home_st.get('distance_km'))} | {_fmt(away_st.get('distance_km'))} |",
                f"| スプリント回数 | {_fmt(home_st.get('sprints'))} | {_fmt(away_st.get('sprints'))} |",
                "",
                "## 3. 主要マッチイベント",
            ]
        )

        if events:
            for ev in events:
                minute = ev.get("minute", "-")
                ev_type = ev.get("type", "EVENT")
                desc = ev.get("description", "")
                pname = ev.get("player_name", "")
                tid = ev.get("team_id", "")
                lines.append(f"- **{minute}'** [{ev_type}] {tid} {pname} {f'({desc})' if desc else ''}".strip())
        else:
            lines.append("- イベント記録なし")

        lines.extend(
            [
                "",
                "## 4. 主な個人スタッツ記録",
            ]
        )

        if notable:
            for p in notable[:5]:
                lines.append(
                    f"- **{p['name']}** ({p['team_id']}): "
                    f"得点 {p['goals']}, アシスト {p['assists']}, "
                    f"xG {p['xg']:.2f}, xA {p['xa']:.2f}, タッチ数 {p['touches']}",
                )
        else:
            lines.append("- 特筆スタッツ選手なし")

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
