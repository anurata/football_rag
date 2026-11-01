# -*- coding: utf-8 -*-
"""
Preview Curation Service (pipeline/preview_curation_service.py).
Supports collaborative preview authoring by generating branch options
with strict Fact/Inference separation and compiling curated preview reports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.preview_fact_extractor import PreviewFactExtractor
from pipeline.preview_markdown_formatter import format_preview_markdown

ROOT_DIR = Path(__file__).resolve().parent.parent


class PreviewCurationService:
    """Service to generate preview decision branches and compile curated reports."""

    def __init__(
        self,
        fact_extractor: Optional[PreviewFactExtractor] = None,
    ) -> None:
        self.extractor = fact_extractor or PreviewFactExtractor()

    def generate_curation_workspace(
        self,
        home_team_id: str,
        away_team_id: str,
        match_date: str = "2026-10-31",
        matchweek: int = 13,
    ) -> Dict[str, Any]:
        """Extract facts and generate tactical branching options for user selection."""
        facts = self.extractor.extract_match_preview_facts(
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            match_date=match_date,
            matchweek=matchweek,
        )
        branches = self._build_preview_branches(facts)
        return {
            "facts": facts,
            "branches": branches,
        }

    def _build_preview_branches(self, facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Construct deterministic decision branches for collaborative selection."""
        home = facts.get("home_team", {})
        away = facts.get("away_team", {})
        home_name = facts.get("basic_info", {}).get("home_team_name", "ホーム")
        away_name = facts.get("basic_info", {}).get("away_team_name", "アウェイ")

        branches: List[Dict[str, Any]] = [
            self._create_lineup_branch(home, home_name, is_home=True),
            self._create_lineup_branch(away, away_name, is_home=False),
            self._create_tactical_scenario_branch(home_name, away_name),
            self._create_matchup_focus_branch(home_name, away_name),
        ]
        return branches

    def _create_lineup_branch(
        self,
        team_profile: Dict[str, Any],
        team_name: str,
        is_home: bool,
    ) -> Dict[str, Any]:
        """Create lineup prediction branch options."""
        pred = team_profile.get("lineup_prediction", {})
        formation = pred.get("formation", "4-2-1-3" if not is_home else "3-4-2-1")
        starters = pred.get("predicted_starters", [])
        bench = pred.get("predicted_bench", [])
        key_bench_player = bench[0]["name"] if bench else "控え主力選手"

        return {
            "branch_id": f"lineup_{'home' if is_home else 'away'}",
            "title": f"【スタメン予想】{team_name} の布陣・先発選定",
            "category": "lineup",
            "options": [
                {
                    "option_id": "A",
                    "label": "前節継続・ベストメンバー固定案",
                    "fact_basis": f"【事実】前節直近の主力先発構成（フォーメーション: {formation}）をベースに維持。",
                    "inference": f"【推測】連勝・好調維持のため戦術的完成度を優先し、前節スタメンを中心に据える公算が高い。",
                },
                {
                    "option_id": "B",
                    "label": f"対戦相手対策・ローテーション案（{key_bench_player} 起用）",
                    "fact_basis": f"【事実】相手の特徴や過密日程に対し、ベンチの有力候補（{key_bench_player}等）が存在。",
                    "inference": f"【推測】相手のプレースタイルへの噛み合わせや走力消耗を考慮し、中盤または前線にテコ入れを行う可能性がある。",
                },
            ],
        }

    def _create_tactical_scenario_branch(
        self,
        home_name: str,
        away_name: str,
    ) -> Dict[str, Any]:
        """Create tactical game-flow scenario branch options."""
        return {
            "branch_id": "tactical_scenario",
            "title": "【試合展開・ゲームシナリオ予想】主導権の所在",
            "category": "game_flow",
            "options": [
                {
                    "option_id": "A",
                    "label": f"{away_name} ハイプレス主導 vs {home_name} 堅守速攻",
                    "fact_basis": f"【事実】{away_name} の高いPPDA/敵陣奪取スタッツと、{home_name} のブロック守備実績。",
                    "inference": f"【推測】{away_name} が前線から即時奪回を仕掛け主導権を握るが、{home_name} は耐えて背後を狙う構図が濃厚。",
                },
                {
                    "option_id": "B",
                    "label": f"中盤の密集戦・互いに隙を見せないロースコア警戒戦",
                    "fact_basis": f"【事実】両チームともに直近失点が少なく、守備組織の安定が際立つ。",
                    "inference": f"【推測】立ち上がりから過度なリスクを冒さず、セットプレーまたは終盤の交代カードが勝敗を分ける展開が想定される。",
                },
                {
                    "option_id": "C",
                    "label": "早い時間帯の先制点でオープンな打ち合いへシフト",
                    "fact_basis": f"【事実】過去の対戦や前半早い時間帯の得点発生傾向。",
                    "inference": f"【推測】立ち上がりの偶発的な得点やミスから一転してインテンシティの高いトランジション合戦になる可能性。",
                },
            ],
        }

    def _create_matchup_focus_branch(
        self,
        home_name: str,
        away_name: str,
    ) -> Dict[str, Any]:
        """Create key matchup focus branch options."""
        return {
            "branch_id": "matchup_focus",
            "title": "【最重要マッチアップ】勝負の焦点",
            "category": "matchup",
            "options": [
                {
                    "option_id": "A",
                    "label": "サイドの攻防: ウイング/SB vs WB/サイドCBの局地戦",
                    "fact_basis": "【事実】両チームのクロス供給数およびサイド攻撃比率の高さ。",
                    "inference": "【推測】サイドの高い位置での1on1の勝敗がペナルティエリア侵入頻度に直結する。",
                },
                {
                    "option_id": "B",
                    "label": "中央の攻防: セカンドボール回収力とネガティブトランジション",
                    "fact_basis": "【事実】ボランチ陣のボール奪取数およびデュエル勝率スタッツ。",
                    "inference": "【推測】中盤のセカンドボールをどちらが支配するかでポゼッション率と前進の安定感が決定づけられる。",
                },
            ],
        }

    def compile_curated_report(
        self,
        facts: Dict[str, Any],
        selections: Dict[str, str],
        custom_insights: Optional[str] = None,
    ) -> str:
        """Compile a curated preview markdown integrating deterministic facts and curated choices."""
        base_md = format_preview_markdown(facts)

        curated_section_lines = [
            "",
            "---",
            "## 🎯 共同キュレーション確定セクション（Curated Focus）",
            "",
            "> [!NOTE]",
            "> 本セクションは自動抽出された客観的事実に基づき、共同対話により合意・確定した戦術予測です。",
            "> 【事実】と【推測】は明確に分離されています。",
            "",
        ]

        # Add chosen branches
        for branch_id, choice_text in selections.items():
            curated_section_lines.append(f"### ◆ {branch_id}")
            curated_section_lines.append(f"{choice_text}")
            curated_section_lines.append("")

        if custom_insights:
            curated_section_lines.extend(
                [
                    "### 💡 アナリスト・共同作成メモ",
                    custom_insights.strip(),
                    "",
                ]
            )

        return base_md + "\n" + "\n".join(curated_section_lines)

    def save_curated_report(
        self,
        output_path: Path,
        content: str,
    ) -> None:
        """Safely write curated report to target output path."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
