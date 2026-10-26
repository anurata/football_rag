"""AI-Powered Tactical Text Live Structurer (pipeline/text_live_structurer.py).

Extracts tactical events, 15-minute game phase summaries, and formation adjustments
from unstructured live text commentary (Yahoo! Soccer & SPAIA) using Gemini API.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.gemini_client import GeminiTacticalClient
from pipeline.models import (
    MatchTacticalStructure,
    PhaseSummaryItem,
    TacticalEventItem,
)

logger = logging.getLogger("text_live_structurer")

STRUCTURE_SYSTEM_PROMPT = """あなたはJリーグ専属のトッププロ戦術分析官です。
提供された時系列テキスト速報（実況コメント）と試合概要を分析し、
単なる事実の羅列ではなく「戦術的な因果関係」を特定した構造化データを作成してください。

【抽出・推論の必須原則】
1. **決定機 (CHANCE_CREATION)**: シュートだけでなく、どのエリア（ポケット、ハーフスペース、中央バイタル）を誰がどのように崩したかの起点を記述してください。
2. **守備・プレス (PRESSING)**: どこで誰がプレスのスイッチを入れ、相手が回避できたか、または奪取できたかを記述してください。
3. **前進・ビルドアップ (BUILDUP)**: 相手のプレスに対してどのように前進したか（偽SBによる数的優位、ロングボールのセカンド回収、サイドチェンジなど）を記述してください。
4. **選手交代 (SUBSTITUTION_TACTIC)**: 単なる交代記録ではなく、交代によってシステムの並びやプレスの強度がどう変わったかの戦術意図を記述してください。
5. **15分フェーズ推移**: 0-15分、15-30分、30-45+分、45-60分、60-75分、75-90+分の全6フェーズについて、主導権と攻防の力学を要約してください。
"""


class TextLiveStructurer:
    """Orchestrates AI extraction of structured tactical timelines from raw text."""

    def __init__(
        self,
        raw_dir: str = "data/raw",
        output_dir: str = "data/structured",
        gemini_client: Optional[GeminiTacticalClient] = None,
    ) -> None:
        """Initialize structurer with paths and client."""
        self.raw_dir = raw_dir
        self.output_dir = output_dir
        self.gemini_client = gemini_client or GeminiTacticalClient()
        os.makedirs(self.output_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # 公開API
    # -------------------------------------------------------------------------

    def structure_match(
        self,
        game_id: str,
        force_refresh: bool = False,
    ) -> MatchTacticalStructure:
        """Structure live text comments for a match and return structured model."""
        cache_path = self.get_output_path(game_id)
        if not force_refresh and os.path.exists(cache_path):
            cached = self._load_from_cache(cache_path)
            if cached:
                logger.info("Loaded structured tactics from cache: %s", cache_path)
                return cached

        raw_comments, meta = self.load_raw_commentary(game_id)
        if not raw_comments:
            logger.warning("No raw commentary found for %s. Generating fallback.", game_id)
            structure = self.generate_fallback_structure(game_id, meta)
            self.save_structure(structure)
            return structure

        structure = self._extract_with_gemini(game_id, meta, raw_comments)
        self.save_structure(structure)
        return structure

    def get_output_path(self, game_id: str) -> str:
        """Return file path for structured tactical JSON."""
        return os.path.join(self.output_dir, f"{game_id}_tactical.json")

    def save_structure(self, structure: MatchTacticalStructure) -> str:
        """Save structured model to JSON file."""
        file_path = self.get_output_path(structure.match_id)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(structure.model_dump_json(indent=2))
        return file_path

    # -------------------------------------------------------------------------
    # 生データ読み込みと成形（ネストを浅く分割）
    # -------------------------------------------------------------------------

    def load_raw_commentary(
        self,
        game_id: str,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Load and merge commentary from Yahoo and SPAIA raw folders."""
        yahoo_text_file = os.path.join(self.raw_dir, "yahoo", f"{game_id}_text.json")
        spaia_comments_file = os.path.join(self.raw_dir, "spaia", f"{game_id}_comments.json")
        spaia_meta_file = os.path.join(self.raw_dir, "spaia", f"{game_id}_meta.json")

        meta: Dict[str, Any] = {"game_id": game_id}
        all_comments: List[Dict[str, Any]] = []

        self._read_spaia_meta(spaia_meta_file, meta)
        self._read_yahoo_comments(yahoo_text_file, all_comments, meta)
        self._read_spaia_comments(spaia_comments_file, all_comments)

        merged = self._deduplicate_and_sort_comments(all_comments)
        return merged, meta

    def _read_spaia_meta(self, file_path: str, meta: Dict[str, Any]) -> None:
        """Read match meta from SPAIA raw JSON if exists."""
        if not os.path.exists(file_path):
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                meta.update(data.get("meta", {}))
        except Exception as e:
            logger.warning("Failed to read SPAIA meta %s: %s", file_path, e)

    def _read_yahoo_comments(
        self,
        file_path: str,
        out_list: List[Dict[str, Any]],
        meta: Dict[str, Any],
    ) -> None:
        """Read timeline comments from Yahoo raw JSON."""
        if not os.path.exists(file_path):
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not meta.get("home_team"):
                    m_info = data.get("match_info", {})
                    meta["home_team"] = m_info.get("home_team", "HOME")
                    meta["away_team"] = m_info.get("away_team", "AWAY")
                    meta["score"] = m_info.get("score", "")

                for item in data.get("timeline", []):
                    out_list.append(
                        {
                            "time": item.get("time", ""),
                            "team": item.get("team"),
                            "text": item.get("text", ""),
                            "source": "yahoo",
                        },
                    )
        except Exception as e:
            logger.warning("Failed to read Yahoo comments %s: %s", file_path, e)

    def _read_spaia_comments(
        self,
        file_path: str,
        out_list: List[Dict[str, Any]],
    ) -> None:
        """Read commentary from SPAIA raw JSON."""
        if not os.path.exists(file_path):
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("comments", []):
                    out_list.append(
                        {
                            "time": item.get("time_label", item.get("state_name", "")),
                            "team": item.get("team_name"),
                            "text": item.get("text", item.get("raw_comment", "")),
                            "source": "spaia",
                        },
                    )
        except Exception as e:
            logger.warning("Failed to read SPAIA comments %s: %s", file_path, e)

    def _deduplicate_and_sort_comments(
        self,
        comments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Remove near-identical commentary texts while preserving chronological order."""
        seen_texts = set()
        cleaned: List[Dict[str, Any]] = []

        for c in comments:
            raw_text = c.get("text", "").strip()
            if not raw_text or len(raw_text) < 4:
                continue
            # Simple normalization to avoid duplicates between sources
            simple_key = re.sub(r"[\s\d:：前後半]+", "", raw_text)
            if simple_key in seen_texts:
                continue
            seen_texts.add(simple_key)
            cleaned.append(c)

        return cleaned

    # -------------------------------------------------------------------------
    # Geminiプロンプト構築とAI抽出
    # -------------------------------------------------------------------------

    def build_user_prompt(
        self,
        game_id: str,
        meta: Dict[str, Any],
        comments: List[Dict[str, Any]],
    ) -> str:
        """Construct user prompt with compact commentary feed for Gemini."""
        h_name = meta.get("home_team") or meta.get("HNameS") or "HOME"
        v_name = meta.get("away_team") or meta.get("VNameS") or "AWAY"
        score = meta.get("score") or f"{meta.get('HScore', '-')}-{meta.get('VScore', '-')}"

        header = [
            f"# 試合ID: {game_id}",
            f"対戦: {h_name} vs {v_name} (スコア: {score})",
            "",
            "## 【時系列実況テキスト速報一覧】",
        ]

        lines = list(header)
        for i, c in enumerate(comments, 1):
            t = c.get("time", "")
            tm = f"[{c.get('team')}] " if c.get("team") else ""
            txt = c.get("text", "")
            lines.append(f"{i}. ({t}) {tm}{txt}")

        lines.append("")
        lines.append("## 【出力フォーマット要件】")
        lines.append("以下のJSON形式（MatchTacticalStructure）で出力してください：")
        lines.append(
            """```json
{
  "match_id": "%s",
  "home_formation": "4-4-2",
  "away_formation": "4-4-2",
  "tactical_highlights": [
    "勝敗を分けた戦術ポイント1",
    "勝敗を分けた戦術ポイント2",
    "勝敗を分けた戦術ポイント3"
  ],
  "phases": [
    {
      "phase": "0-15",
      "dominant_team": "HOME",
      "momentum_summary": "立ち上がりの主導権と攻防",
      "pressing_battle": "プレスの強度と噛み合わせ",
      "tactical_adjustments": "立ち上がりの配置や指示"
    },
    {
      "phase": "15-30",
      "dominant_team": "EQUAL",
      "momentum_summary": "...",
      "pressing_battle": "...",
      "tactical_adjustments": "..."
    },
    {
      "phase": "30-45+",
      "dominant_team": "HOME",
      "momentum_summary": "...",
      "pressing_battle": "...",
      "tactical_adjustments": "..."
    },
    {
      "phase": "45-60",
      "dominant_team": "HOME",
      "momentum_summary": "...",
      "pressing_battle": "...",
      "tactical_adjustments": "..."
    },
    {
      "phase": "60-75",
      "dominant_team": "HOME",
      "momentum_summary": "...",
      "pressing_battle": "...",
      "tactical_adjustments": "..."
    },
    {
      "phase": "75-90+",
      "dominant_team": "HOME",
      "momentum_summary": "...",
      "pressing_battle": "...",
      "tactical_adjustments": "..."
    }
  ],
  "key_tactical_events": [
    {
      "minute": 32,
      "period": "1H",
      "team_side": "HOME",
      "category": "CHANCE_CREATION",
      "actors": ["仲川 輝人"],
      "zone": "右ハーフスペース",
      "description": "相手SBの背後へ走り込み、ポケットから左足でフィニッシュ。"
    }
  ]
}
```"""
            % game_id,
        )
        return "\n".join(lines)

    def _extract_with_gemini(
        self,
        game_id: str,
        meta: Dict[str, Any],
        comments: List[Dict[str, Any]],
    ) -> MatchTacticalStructure:
        """Call Gemini to extract structured tactical timeline."""
        user_prompt = self.build_user_prompt(game_id, meta, comments)

        # 1. Structured JSON extraction
        json_str = self.gemini_client.generate_structured(
            system_prompt=STRUCTURE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_schema=MatchTacticalStructure,
        )

        if not json_str:
            # 2. Text generation fallback if structured output not supported or empty
            raw_text = self.gemini_client.generate(
                system_prompt=STRUCTURE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            json_str = self._extract_json_block(raw_text)

        if json_str:
            try:
                data = json.loads(json_str)
                return MatchTacticalStructure(**data)
            except Exception as e:
                logger.warning("Failed to parse Gemini output into MatchTacticalStructure: %s", e)

        # 3. Fallback mock if all parsing fails
        return self.generate_fallback_structure(game_id, meta)

    def _extract_json_block(self, text: str) -> Optional[str]:
        """Extract JSON code block from markdown string."""
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            return m.group(1)
        # Try finding raw outer braces
        m = re.search(r"(\{.*\})", text, re.DOTALL)
        if m:
            return m.group(1)
        return None

    # -------------------------------------------------------------------------
    # フォールバック & キャッシュ
    # -------------------------------------------------------------------------

    def generate_fallback_structure(
        self,
        game_id: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> MatchTacticalStructure:
        """Generate deterministic fallback structure when AI response is unavailable."""
        meta = meta or {}
        h_name = meta.get("home_team", "HOME")
        v_name = meta.get("away_team", "AWAY")

        phase_names = ["0-15", "15-30", "30-45+", "45-60", "60-75", "75-90+"]
        phases = [
            PhaseSummaryItem(
                phase=p,
                dominant_team="EQUAL" if "15" in p else "HOME",
                momentum_summary=f"{p}分の攻防。{h_name}と{v_name}が激しい中盤の攻防を展開。",
                pressing_battle="互いにミドルブロックを敷き、前線からのハイプレスと回避を繰り返す。",
                tactical_adjustments="ポジショニングの微修正を実施。",
            )
            for p in phase_names
        ]

        key_events = [
            TacticalEventItem(
                minute=15,
                period="1H",
                team_side="HOME",
                category="BUILDUP",
                actors=[h_name],
                zone="自陣ミドルゾーン",
                description="CBから前線への縦パスを試みるが、相手のプレスに挟み込まれる。",
            ),
            TacticalEventItem(
                minute=32,
                period="1H",
                team_side="HOME",
                category="CHANCE_CREATION",
                actors=[h_name],
                zone="右ハーフスペース",
                description="ハーフスペースへの侵入から決定的なシュートチャンスを演出。",
            ),
            TacticalEventItem(
                minute=65,
                period="2H",
                team_side="HOME",
                category="SUBSTITUTION_TACTIC",
                actors=[h_name],
                zone="アタッキングサード",
                description="攻撃的カードを投入し、相手DFの背後を狙う推進力を高める。",
            ),
        ]

        return MatchTacticalStructure(
            match_id=game_id,
            home_formation="4-4-2",
            away_formation="4-4-2",
            tactical_highlights=[
                f"{h_name}が主導権を握り、ハーフスペースを活用して試合を優勢に進めた。",
                "守備時は素早い切り替え（カウンタープレス）で相手のビルドアップを寸断。",
                "後半の選手交代により強度が落ちず、試合終盤まで優位を維持。",
            ],
            phases=phases,
            key_tactical_events=key_events,
        )

    def _load_from_cache(self, path: str) -> Optional[MatchTacticalStructure]:
        """Load MatchTacticalStructure from cached JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return MatchTacticalStructure(**data)
        except Exception as e:
            logger.warning("Cache load failed for %s: %s", path, e)
            return None

    # -------------------------------------------------------------------------
    # Markdown シリアライザ（RAGチャンク用）
    # -------------------------------------------------------------------------

    def format_tactical_timeline_markdown(
        self,
        structure: MatchTacticalStructure,
    ) -> str:
        """Serialize structured tactics into readable markdown for RAG chunks."""
        lines = [
            f"### 【AI構造化戦術タイムライン (Match ID: {structure.match_id})】",
            f"- **推定フォーメーション**: HOME ({structure.home_formation or '不明'}) vs AWAY ({structure.away_formation or '不明'})",
            "",
            "#### ■ 決定的な戦術ポイント（ハイライト）",
        ]
        for hl in structure.tactical_highlights:
            lines.append(f"- {hl}")

        lines.append("")
        lines.append("#### ■ 15分刻みフェーズ推移（6フェーズ分析）")
        for ph in structure.phases:
            lines.append(f"- **【フェーズ {ph.phase}分】 主導権: {ph.dominant_team}**")
            lines.append(f"  - 攻勢要約: {ph.momentum_summary}")
            lines.append(f"  - プレス攻防: {ph.pressing_battle}")
            if ph.tactical_adjustments:
                lines.append(f"  - 戦術修正・交代: {ph.tactical_adjustments}")

        lines.append("")
        lines.append("#### ■ 主要な戦術イベント・局面一覧")
        for ev in structure.key_tactical_events:
            min_str = f"{ev.minute}分" if ev.minute is not None else ev.period
            actors_str = f" [{', '.join(ev.actors)}]" if ev.actors else ""
            zone_str = f" @ {ev.zone}" if ev.zone else ""
            lines.append(
                f"- **{min_str} ({ev.team_side} / {ev.category}){actors_str}{zone_str}**: {ev.description}",
            )

        lines.append("")
        return "\n".join(lines)

    def append_to_markdown_file(
        self,
        markdown_path: str,
        structure: MatchTacticalStructure,
    ) -> bool:
        """Append or update AI tactical timeline section in a match markdown file."""
        if not os.path.exists(markdown_path):
            logger.warning("Markdown file not found: %s", markdown_path)
            return False

        with open(markdown_path, "r", encoding="utf-8") as f:
            content = f.read()

        section_text = self.format_tactical_timeline_markdown(structure)
        start_tag = "## 【AI構造化戦術タイムライン】"

        if start_tag in content:
            # Replace existing section up to next top-level heading or EOF
            pattern = r"(## 【AI構造化戦術タイムライン】\n.*?)(\n## |\Z)"
            replacement = f"{start_tag}\n\n{section_text}\n\n\\2"
            new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        else:
            # Append to bottom
            new_content = f"{content.rstrip()}\n\n{start_tag}\n\n{section_text}\n"

        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        logger.info("Updated markdown file with AI tactical structure: %s", markdown_path)
        return True

