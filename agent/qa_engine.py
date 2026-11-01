"""
agent/qa_engine.py

Tactical QA Engine for J-League Match Analysis & Viewing Navigation.
Connects SQLite database stats, 15 tactical perspectives, match context,
and Gemini API (with optional Google Search Grounding) for deep reasoning.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.gemini_client import GeminiTacticalClient
from agent.objective_profiler import resolve_team_name
from pipeline.db import DEFAULT_DB_PATH, get_db_connection

logger = logging.getLogger(__name__)


class TacticalQAEngine:
    """Core QA engine that unifies RAG context and Gemini Search Grounding."""

    def __init__(
        self,
        gemini_client: Optional[GeminiTacticalClient] = None,
        db_path: str = DEFAULT_DB_PATH,
        structured_dir: str = "data/structured",
        mock_mode: bool = False,
    ) -> None:
        self.gemini_client = gemini_client or GeminiTacticalClient(mock_mode=mock_mode)
        self.db_path = Path(db_path)
        self.structured_dir = Path(structured_dir)

    def ask(
        self,
        question: str,
        match_id: Optional[str] = None,
        enable_web_search: bool = False,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Execute QA session with contextual RAG and optional Google Search Grounding."""
        context_text, meta_summary = self._build_context(match_id)
        sys_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            question=question,
            context_text=context_text,
            enable_web_search=enable_web_search,
        )

        qa_res = self.gemini_client.generate_qa(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            enable_google_search=enable_web_search,
            temperature=temperature,
        )

        return {
            "question": question,
            "answer": qa_res.get("text", ""),
            "match_id": match_id,
            "web_search_enabled": enable_web_search,
            "web_search_queries": qa_res.get("web_search_queries", []),
            "grounding_sources": qa_res.get("grounding_sources", []),
            "model_used": qa_res.get("model_used", ""),
            "context_summary": meta_summary,
        }

    def _build_system_prompt(self) -> str:
        """Construct the system prompt for the professional tactical analyst."""
        return (
            "あなたはJリーグ公認のプロサッカー戦術アナリスト兼観戦ナビゲーターです。\n"
            "蓄積された試合データ（基本スタッツ、進入変換率、15観点戦術分析、怪我・警告・過密日程などの前提条件）"
            "および必要に応じて提供されるWeb検索グラウンディング情報を基に、論理的かつ説得力のある回答をしてください。\n\n"
            "【回答の指針】\n"
            "1. 【客観的事実と因果】：単なる印象論ではなく、数値データやピッチ外の外部要因（中◯日の休養差、怪我人、警告リーチ）を結びつけて「なぜそれが起きたか」を説明すること。\n"
            "2. 【観戦レンズの提示】：ユーザーがスタジアムやDAZNで試合を観戦する際、「どこに注目すると面白いか（時間帯・スペース・選手対決）」を具体的にアドバイスすること。\n"
            "3. 【Web検索の活用】：最新の公式発表や移籍・怪我・監督コメントについては、検索された事実関係を正確に反映し、データにない点は推測と明示すること。\n"
            "4. 【構成】：スマートフォン等でも読みやすいよう、箇条書きや強調（太字）を活用して簡潔明瞭に整理すること。"
        )

    def _build_user_prompt(
        self,
        question: str,
        context_text: str,
        enable_web_search: bool,
    ) -> str:
        """Compose the user prompt integrating context and user inquiry."""
        parts = []
        if context_text:
            parts.append("### 【対象試合の蓄積データ ＆ コンテキスト】")
            parts.append(context_text)
            parts.append("\n" + "=" * 40 + "\n")

        parts.append(f"### 【ユーザーからの質問】\n{question}")

        if enable_web_search:
            parts.append(
                "\n※Web検索機能が有効です。ピッチ外の最新公式発表や直近動向が必要な場合は、検索情報を補完して回答してください。"
            )

        return "\n".join(parts)

    def _build_context(self, match_id: Optional[str]) -> Tuple[str, str]:
        """Fetch and aggregate match context from SQLite and structured JSON."""
        if not match_id:
            return self._build_global_context()

        db_match = self._fetch_db_match(match_id)
        struct_data = self._load_structured_json(match_id)

        blocks = []
        meta_lines = []

        if db_match:
            h_name = resolve_team_name(db_match.get("home_team_id"))
            a_name = resolve_team_name(db_match.get("away_team_id"))
            h_score = db_match.get("home_score", 0)
            a_score = db_match.get("away_score", 0)
            mw = db_match.get("matchweek", 0)
            stadium = db_match.get("stadium", "")
            date = db_match.get("date", "")

            title = f"2026 J1 第{mw}節: {h_name} {h_score} - {a_score} {a_name} ({date} @{stadium})"
            meta_lines.append(title)
            blocks.append(f"【試合概要】: {title}")

        if struct_data:
            # 1. Match Context (外部前提)
            ctx = struct_data.get("match_context") or {}
            ctx_summary = self._format_match_context(ctx)
            if ctx_summary:
                blocks.append(f"【試合前提サポート要因】:\n{ctx_summary}")

            # 2. Key Tactical Perspectives (15観点の要約)
            perspectives = struct_data.get("tactical_perspectives") or {}
            p_summary = self._format_perspectives(perspectives)
            if p_summary:
                blocks.append(f"【戦術15観点ハイライト】:\n{p_summary}")

            # 3. Match Summary / Metrics
            m_summary = struct_data.get("match_summary") or {}
            if m_summary:
                blocks.append(f"【定量スタッツ要約】:\n{json.dumps(m_summary, ensure_ascii=False, indent=2)}")

        full_context = "\n\n".join(blocks)
        meta_str = " / ".join(meta_lines) if meta_lines else "全般コンテキスト"
        return full_context, meta_str

    def _build_global_context(self) -> Tuple[str, str]:
        """Provide general dataset context when no specific match is selected."""
        summary = (
            "【全般コンテキスト】\n"
            "本システムは2026年明治安田J1リーグの全試合データを保持しています。\n"
            "FC東京を中心に、全20クラブのスタッツ・戦術15観点・ピッチ外コンテキスト（過密日程・怪我・警告・ローン制限）を分析可能です。"
        )
        return summary, "全クラブ共通・2026シーズン"

    def _fetch_db_match(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Fetch basic match metadata from SQLite."""
        if not self.db_path.exists():
            return None

        try:
            conn = get_db_connection(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM matches WHERE match_id = ?",
                (match_id,),
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(row)
        except Exception as e:
            logger.warning("Error fetching match %s: %s", match_id, e)

        return None

    def _load_structured_json(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Load tactical structured JSON from storage."""
        target = self.structured_dir / f"{match_id}_tactical.json"
        if not target.exists():
            return None

        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Error reading structured json for %s: %s", match_id, e)
            return None

    def _format_match_context(self, ctx: Dict[str, Any]) -> str:
        """Format 5 external context dimensions into concise text."""
        lines = []

        injuries = ctx.get("injuries_and_conditions") or []
        if injuries:
            lines.append("- 怪我・コンディション: " + "; ".join(str(i) for i in injuries[:3]))

        cards = ctx.get("yellow_accumulation") or []
        if cards:
            lines.append("- 累積警告・停止リスク: " + "; ".join(str(c) for c in cards[:3]))

        schedule = ctx.get("schedule_density") or {}
        if schedule:
            lines.append(f"- 過密日程: {schedule.get('description', json.dumps(schedule, ensure_ascii=False))}")

        climate = ctx.get("climate_and_pitch") or {}
        if climate:
            lines.append(f"- 気候・ピッチ状態: {climate.get('description', json.dumps(climate, ensure_ascii=False))}")

        loan = ctx.get("loan_restrictions") or []
        if loan:
            lines.append("- 期限付き移籍制限: " + "; ".join(str(l) for l in loan))

        return "\n".join(lines)

    def _format_perspectives(self, perspectives: Dict[str, Any]) -> str:
        """Select and summarize top tactical perspectives."""
        lines = []
        for key, val in list(perspectives.items())[:6]:
            if isinstance(val, dict):
                desc = val.get("analysis") or val.get("summary") or str(val)
                lines.append(f"- **{key}**: {desc[:150]}")
            elif isinstance(val, str):
                lines.append(f"- **{key}**: {val[:150]}")
        return "\n".join(lines)
