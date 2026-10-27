"""
scripts/export_notebooklm.py

Export structured tactical analyses, deep metrics, qualitative reviews,
and tactical theory knowledge into optimized Markdown documents for Google NotebookLM.
Enables instant, in-depth tactical RAG hypothesis verification on smartphones & desktop.
"""

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Setup root directory
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import yaml
from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from agent.objective_profiler import resolve_team_name, TEAM_NAME_MAP
from agent.player_rater import PlayerRatingGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class NotebookLMExporter:
    """Exports football tactical RAG data into curated Markdown files for Google NotebookLM."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        structured_dir: str = "data/structured",
        knowledge_dir: str = "knowledge",
        output_dir: str = "exports/notebooklm",
    ) -> None:
        self.db_path = Path(db_path)
        self.structured_dir = Path(structured_dir)
        self.knowledge_dir = Path(knowledge_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.player_rater = PlayerRatingGenerator()

    def export_all(self) -> List[Path]:
        """Execute all export tasks and return generated file paths."""
        logger.info("Starting NotebookLM export pipeline...")
        exported_files: List[Path] = []

        # 1. Tactical Knowledge Base
        p_knowledge = self.export_tactical_knowledge()
        if p_knowledge:
            exported_files.append(p_knowledge)

        # 2. FC Tokyo 2026 Season Tactical Dossier
        p_fct = self.export_fctokyo_dossier()
        if p_fct:
            exported_files.append(p_fct)

        # 3. Matchweek Reviews (Grouped batches)
        mw_files = self.export_matchweek_reviews(batch_size=4)
        exported_files.extend(mw_files)

        # 4. Player Ratings Summary
        p_players = self.export_player_ratings()
        if p_players:
            exported_files.append(p_players)

        # 5. NotebookLM Tactical Prompt Guide
        p_guide = self.export_prompt_guide()
        if p_guide:
            exported_files.append(p_guide)

        logger.info(
            "NotebookLM export complete. Total %d source documents generated in '%s'",
            len(exported_files),
            self.output_dir,
        )
        return exported_files

    # =========================================================================
    # 1. Tactical Knowledge Base Export
    # =========================================================================

    def export_tactical_knowledge(self) -> Optional[Path]:
        """Compile metric causal trees, trade-offs, system matrix, and archetypes into Markdown."""
        out_path = self.output_dir / "00_戦術分析理論_ナレッジ体系.md"
        lines: List[str] = [
            "# Jリーグ戦術分析ナレッジ体系＆理論ベース",
            "",
            "> 本ドキュメントは、Jリーグの試合データや戦術現象を論理的・因果的に読み解くための戦術理論、指標因果関係、フォーメーション噛み合わせ、選手役割定義をまとめたマスター知識ベースです。",
            "",
        ]

        # 1.1 Tactical Trade-offs
        tradeoff_path = self.knowledge_dir / "tactical_tradeoffs.yaml"
        if tradeoff_path.exists():
            lines.append("## 1. 戦術トレードオフ原則 (Tactical Trade-offs)")
            lines.append("戦術的決断・配置変更における「主作用（メリット・狙い）」と「副作用（構造的リスク・弱点）」のペア定義です。\n")
            try:
                data = yaml.safe_load(tradeoff_path.read_text(encoding="utf-8"))
                for item in data.get("tradeoffs", []):
                    name = item.get("tactic_name", "戦術選択")
                    mech = item.get("core_mechanism", "")
                    lines.append(f"### ◆ {name}")
                    if mech:
                        lines.append(f"- **基本メカニズム**: {mech}")
                    
                    # Main effects
                    m_effects = item.get("main_effects", [])
                    if m_effects:
                        lines.append("- **主作用（メリット・狙い）**:")
                        for eff in m_effects:
                            lines.append(f"  - *{eff.get('summary', '')}*: {eff.get('description', '')}")
                    
                    # Side effects
                    s_effects = item.get("side_effects", [])
                    if s_effects:
                        lines.append("- **副作用（構造的リスク・弱点）**:")
                        for risk in s_effects:
                            lines.append(f"  - *{risk.get('risk_name', '')} [{risk.get('severity', '')}]*: {risk.get('description', '')}")

                    # Countermeasures
                    counters = item.get("countermeasures", [])
                    if counters:
                        lines.append("- **対策・打ち手 (Countermeasures)**:")
                        for c in counters:
                            lines.append(f"  - {c}")
                    lines.append("")
            except Exception as e:
                logger.warning("Failed parsing %s: %s", tradeoff_path, e)

        # 1.2 Metric Causal Trees
        causal_path = self.knowledge_dir / "metric_causal_trees.yaml"
        if causal_path.exists():
            lines.append("## 2. スタッツ因果ツリー (Metric Causal Trees)")
            lines.append("スタッツ数値の増減から複数の戦術的仮説と検証ロジックを導く因果ネットワークです。\n")
            try:
                data = yaml.safe_load(causal_path.read_text(encoding="utf-8"))
                for tree in data.get("trees", []):
                    metric = tree.get("metric_name", "")
                    phenom = tree.get("phenomenon", "")
                    lines.append(f"### 指標: {metric}")
                    if phenom:
                        lines.append(f"*{phenom}*")
                    for hyp in tree.get("hypotheses", []):
                        h_name = hyp.get("name", "")
                        h_desc = hyp.get("description", "")
                        lines.append(f"- **【仮説】{h_name}**: {h_desc}")
                        v_metrics = hyp.get("verification_metrics", [])
                        if v_metrics:
                            v_text = ", ".join([f"{v.get('metric')}({v.get('expected_pattern')})" for v in v_metrics])
                            lines.append(f"  - 検証指標: {v_text}")
                        elim = hyp.get("elimination_condition", "")
                        if elim:
                            lines.append(f"  - 棄却条件: {elim}")
                    lines.append("")
            except Exception as e:
                logger.warning("Failed parsing %s: %s", causal_path, e)

        # 1.3 System Compatibility Matrix
        sys_path = self.knowledge_dir / "system_matrix.yaml"
        if sys_path.exists():
            lines.append("## 3. フォーメーション相性と噛み合わせマトリクス")
            lines.append("システム間の構造的優位、ピン留めの力学、ハーフスペースの空間ミスマッチです。\n")
            try:
                data = yaml.safe_load(sys_path.read_text(encoding="utf-8"))
                for entry in data.get("matchups", []):
                    name = entry.get("name", "")
                    h_form = entry.get("home_formation", "")
                    a_form = entry.get("away_formation", "")
                    lines.append(f"### ◆ {name}")
                    
                    # Advantages
                    h_advs = entry.get("structural_advantages_for_home", [])
                    if h_advs:
                        lines.append(f"- **{h_form}側の構造的優位**:")
                        for adv in h_advs:
                            lines.append(f"  - {adv.get('zone', '')}: {adv.get('description', '')}")

                    a_advs = entry.get("structural_advantages_for_away", [])
                    if a_advs:
                        lines.append(f"- **{a_form}側の構造的優位**:")
                        for adv in a_advs:
                            lines.append(f"  - {adv.get('zone', '')}: {adv.get('description', '')}")

                    pins = entry.get("pinning_mechanisms", [])
                    if pins:
                        lines.append(f"- **ピン留め・空間の力学**:")
                        for p in pins:
                            lines.append(f"  - {p}")
                    lines.append("")
            except Exception as e:
                logger.warning("Failed parsing %s: %s", sys_path, e)

        # 1.4 Player Archetypes
        arch_path = self.knowledge_dir / "player_archetypes.json"
        if arch_path.exists():
            lines.append("## 4. 選手アーキタイプ（プレースタイル分類）")
            lines.append("選手の役割・タスク定義です。\n")
            try:
                arch_data = json.loads(arch_path.read_text(encoding="utf-8"))
                archetypes_list = arch_data.get("archetypes", [])
                for entry in archetypes_list:
                    name_ja = entry.get("name", "")
                    role = entry.get("archetype_id", "")
                    pos = entry.get("position_group", "")
                    desc = entry.get("description", "")
                    funcs = " / ".join(entry.get("tactical_functions", []))
                    lines.append(f"### ◆ {name_ja} [{pos}] ({role})")
                    lines.append(f"- **定義**: {desc}")
                    if funcs:
                        lines.append(f"- **戦術的機能**: {funcs}")
                    lines.append("")
            except Exception as e:
                logger.warning("Failed parsing %s: %s", arch_path, e)

        out_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Exported Tactical Knowledge Base -> %s", out_path)
        return out_path

    # =========================================================================
    # 2. FC Tokyo 2026 Season Tactical Dossier
    # =========================================================================

    def export_fctokyo_dossier(self) -> Optional[Path]:
        """Compile all FC Tokyo matches in 2026 into a chronological tactical dossier."""
        out_path = self.output_dir / "01_FC東京_2026戦術推移カルテ.md"
        matches = self._fetch_matches_for_team(team_id="FCT", season=2026)

        if not matches:
            logger.warning("No matches found for FC Tokyo in season 2026.")
            return None

        lines: List[str] = [
            "# FC東京 2026シーズン 戦術カルテ＆推移ドシエ",
            "",
            "> 2026シーズンのFC東京（松橋力蔵体制等）の全公式戦における戦術的変化、フェーズ別主導権、進入変換率、CBP評価、選手寸評を時系列で網羅した詳細カルテです。",
            "",
            "## シーズン概要サマリー",
            f"- 総対象試合数: {len(matches)}試合",
            "",
            "---",
            "",
        ]

        for match in matches:
            m_id = match["match_id"]
            structured_data = self._load_structured_json(m_id)
            match_md = self._format_single_match_section(match, structured_data, focus_team="FCT")
            lines.append(match_md)
            lines.append("\n---\n")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Exported FC Tokyo Dossier -> %s", out_path)
        return out_path

    # =========================================================================
    # 3. Matchweek Reviews Export
    # =========================================================================

    def export_matchweek_reviews(self, batch_size: int = 4) -> List[Path]:
        """Group all matches into matchweek batches and generate markdown files."""
        all_matches = self._fetch_all_matches(season=2026)
        if not all_matches:
            return []

        # Group by matchweek
        mw_dict: Dict[int, List[Dict[str, Any]]] = {}
        for m in all_matches:
            mw = m.get("matchweek") or 0
            mw_dict.setdefault(mw, []).append(m)

        sorted_mws = sorted(mw_dict.keys())
        exported_paths: List[Path] = []

        # Split into batches of `batch_size` matchweeks
        for i in range(0, len(sorted_mws), batch_size):
            batch_mws = sorted_mws[i : i + batch_size]
            start_mw = batch_mws[0]
            end_mw = batch_mws[-1]

            filename = f"02_2026シーズン_戦術レビュー_第{start_mw:02d}節-第{end_mw:02d}節.md"
            out_path = self.output_dir / filename

            lines: List[str] = [
                f"# 2026 J1リーグ 戦術レビュー（第{start_mw}節 〜 第{end_mw}節）",
                "",
                f"> 第{start_mw}節から第{end_mw}節における全試合の15視点プロファイル、進入変換率、プレッシング攻防、重要戦術イベントを網羅した戦術ドキュメントです。",
                "",
            ]

            for mw in batch_mws:
                mw_matches = mw_dict[mw]
                lines.append(f"## ■ 第 {mw} 節（全 {len(mw_matches)} 試合）\n")
                for m in mw_matches:
                    m_id = m["match_id"]
                    structured_data = self._load_structured_json(m_id)
                    single_doc = self._format_single_match_section(m, structured_data)
                    lines.append(single_doc)
                    lines.append("\n")

            out_path.write_text("\n".join(lines), encoding="utf-8")
            logger.info("Exported Matchweek Batch -> %s", out_path)
            exported_paths.append(out_path)

        return exported_paths

    # =========================================================================
    # 4. Player Ratings Summary
    # =========================================================================

    def export_player_ratings(self) -> Optional[Path]:
        """Aggregate player ratings and CBP metrics across matches from structured tactical files."""
        out_path = self.output_dir / "03_全選手パフォーマンス_レーティング一覧.md"

        # Accumulate metrics per player
        players_attack: Dict[str, Dict[str, Any]] = {}
        players_defense: Dict[str, Dict[str, Any]] = {}
        players_gain: Dict[str, Dict[str, Any]] = {}
        players_pass: Dict[str, Dict[str, Any]] = {}

        for json_file in self.structured_dir.glob("*_tactical.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            deep_m = data.get("deep_metrics", {})
            cbp_ranks = deep_m.get("cbp_rankings", {})
            if not cbp_ranks:
                continue

            for side in ["home", "away"]:
                side_data = cbp_ranks.get(side, {})

                # Attack
                for p in side_data.get("top_attack", []):
                    name = p.get("name")
                    val = float(p.get("value", 0.0))
                    if name:
                        rec = players_attack.setdefault(name, {"count": 0, "max": 0.0, "total": 0.0})
                        rec["count"] += 1
                        rec["total"] += val
                        rec["max"] = max(rec["max"], val)

                # Defense
                for p in side_data.get("top_defense", []):
                    name = p.get("name")
                    val = float(p.get("value", 0.0))
                    if name:
                        rec = players_defense.setdefault(name, {"count": 0, "max": 0.0, "total": 0.0})
                        rec["count"] += 1
                        rec["total"] += val
                        rec["max"] = max(rec["max"], val)

                # Gain (Ball Recovery)
                for p in side_data.get("top_gain", []):
                    name = p.get("name")
                    val = float(p.get("value", 0.0))
                    if name:
                        rec = players_gain.setdefault(name, {"count": 0, "max": 0.0, "total": 0.0})
                        rec["count"] += 1
                        rec["total"] += val
                        rec["max"] = max(rec["max"], val)

                # Pass
                for p in side_data.get("top_pass", []):
                    name = p.get("name")
                    val = float(p.get("value", 0.0))
                    if name:
                        rec = players_pass.setdefault(name, {"count": 0, "max": 0.0, "total": 0.0})
                        rec["count"] += 1
                        rec["total"] += val
                        rec["max"] = max(rec["max"], val)

        lines: List[str] = [
            "# 2026シーズン 選手パフォーマンス＆スタッツ評価名鑑",
            "",
            "> 2026シーズンの全試合における選手のCBP（チャンスビルディングポイント）客観データを集約したパフォーマンス名鑑です。",
            "NotebookLMで「今季ボール奪取で最も貢献した選手は誰？」「攻撃CBP上位の選手とその特徴は？」等の仮説検証に活用できます。",
            "",
        ]

        def _render_ranking_table(title: str, category_name: str, p_dict: Dict[str, Dict[str, Any]]) -> None:
            sorted_items = sorted(
                p_dict.items(),
                key=lambda x: (x[1]["max"], x[1]["total"]),
                reverse=True,
            )[:40]
            lines.append(f"## {title}")
            lines.append(f"| 順位 | 選手名 | 1試合最高{category_name} | ランクイン回数 | 累計{category_name} |")
            lines.append("| :---: | :--- | :---: | :---: | :---: |")
            for rank, (name, stats) in enumerate(sorted_items, 1):
                max_v = f"{stats['max']:.2f}"
                cnt = f"{stats['count']}試合"
                tot_v = f"{stats['total']:.2f}"
                lines.append(f"| {rank} | {name} | {max_v} | {cnt} | {tot_v} |")
            lines.append("\n")

        _render_ranking_table("1. 攻撃貢献度（攻撃CBP）トッププレーヤー", "攻撃CBP", players_attack)
        _render_ranking_table("2. 守備貢献度（守備CBP）トッププレーヤー", "守備CBP", players_defense)
        _render_ranking_table("3. ボール奪取（奪取CBP）マスター", "奪取CBP", players_gain)
        _render_ranking_table("4. パス配給（パスCBP）オーガナイザー", "パスCBP", players_pass)

        out_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Exported Player Ratings -> %s", out_path)
        return out_path

    # =========================================================================
    # 5. NotebookLM Tactical Prompt Guide
    # =========================================================================

    def export_prompt_guide(self) -> Path:
        """Create a prompt cheat-sheet for user to ask Gemini in NotebookLM."""
        out_path = self.output_dir / "04_NotebookLM_戦術仮説検証プロンプト集.md"
        content = """# NotebookLM（Gemini Notebook）戦術仮説検証プロンプト集

スマホやPCのNotebookLMで、本ソース群を読み込ませた状態でそのままコピー＆ペーストして使える実践的プロンプト集です。

---

## 1. 試合の敗因・勝因の多角検証
```text
【プロンプト】
2026年8月8日の町田ゼルビア戦において、FC東京が1-5で大敗した要因を以下の3つの視点から分析してください：
1. 構造的要因（フォーメーション噛み合わせ、立ち位置）
2. 偶発的要因・分岐点（退場、選手交代の影響）
3. スタッツの裏付け（進入変換率、Field Tilt、CBPの差）
その上で、次回町田と対戦する際の具体的な戦術的対策を提示してください。
```

---

## 2. プレッシングとビルドアップの力学検証
```text
【プロンプト】
FC東京の今シーズンのハイプレスが機能した試合と、プレスを回避されて失点した試合を比較してください。
特に中盤ボランチ（高宇洋、稲村隼翔）のフィルター強度と、前線からの連動守備における課題を抽出してください。
```

---

## 3. 選手パフォーマンス＆スタメン選考の検証
```text
【プロンプト】
2026シーズンにおいて、攻撃面で最もチームに貢献（CBP攻撃、進入率）しているキーマン3名と、守備面で高い数値を残しているキーマン3名を挙げてください。
また、交代出場で最も流れを変えた「ジョーカー」選手は誰ですか？
```

---

## 4. 次節対戦相手のスカウティング＆対策シミュレーション
```text
【プロンプト】
FC東京が次に対戦する相手チームの直近数試合の戦術傾向（攻撃の進入ルート、被シュート時の弱点、守備ブロックの脆弱エリア）を分析し、
FC東京が突くべき「ハーフスペース」「背後のスペース」および推奨フォーメーションを提案してください。
```

---

## 5. 5人交代制マネジメントの評価
```text
【プロンプト】
今シーズンのFC東京の後半の失点パターンと、ベンチ交代インパクト（交代選手のCBP貢献度）を検証してください。
交代カードを切るタイミングや投入選手の特徴について、戦術理論の観点から改善提案を行ってください。
```
"""
        out_path.write_text(content, encoding="utf-8")
        logger.info("Exported Prompt Guide -> %s", out_path)
        return out_path

    # =========================================================================
    # Formatting Helpers (Small, modular methods)
    # =========================================================================

    def _format_single_match_section(
        self,
        match: Dict[str, Any],
        structured_data: Optional[Dict[str, Any]],
        focus_team: Optional[str] = None,
    ) -> str:
        """Format an entire match into a clear, cohesive markdown section."""
        home_name = resolve_team_name(match.get("home_team_id"))
        away_name = resolve_team_name(match.get("away_team_id"))
        h_score = match.get("home_score", "-")
        a_score = match.get("away_score", "-")
        mw = match.get("matchweek")
        mw_str = f"第 {mw} 節" if mw else "実戦検証マッチ"
        dt = match.get("date", "日程未定")
        stadium = match.get("stadium", "スタジアム")

        lines: List[str] = [
            f"### 【{mw_str}】{dt} : {home_name} {h_score} - {a_score} {away_name}",
            f"- **会場**: {stadium} | **天候**: {match.get('weather', '不明')} | **観客**: {match.get('attendance', 0):,}人",
        ]

        if not structured_data:
            lines.append("- *(※詳細な構造化戦術データは準備中)*")
            return "\n".join(lines)

        # Formations
        h_form = structured_data.get("home_formation", "不明")
        a_form = structured_data.get("away_formation", "不明")
        lines.append(f"- **システム配置**: {home_name} [{h_form}] vs [{a_form}] {away_name}")
        lines.append("")

        # Highlights
        highlights = structured_data.get("tactical_highlights", [])
        if highlights:
            lines.append("#### 戦術ハイライト")
            for hl in highlights:
                lines.append(f"- {hl}")
            lines.append("")

        # Deep Metrics Summary
        deep_m = structured_data.get("deep_metrics", {})
        if deep_m:
            lines.append("#### 定量スタッツ・進入効率（Deep Metrics）")
            lines.append(self._format_deep_metrics_table(deep_m, home_name, away_name))
            lines.append("")

        # Phases
        phases = structured_data.get("phases", [])
        if phases:
            lines.append("#### 時間帯別（15分刻み）戦術ダイナミクス")
            for p in phases:
                phase_name = p.get("phase", "")
                dominant = p.get("dominant_team", "")
                dom_label = home_name if dominant == "HOME" else (away_name if dominant == "AWAY" else "互角")
                lines.append(f"**[{phase_name}分 - 主導権: {dom_label}]**")
                lines.append(f"- **戦況展開**: {p.get('momentum_summary', '')}")
                lines.append(f"- **プレッシング攻防**: {p.get('pressing_battle', '')}")
                lines.append(f"- **ベンチ戦術修正**: {p.get('tactical_adjustments', '')}")
                lines.append("")

        # 3-Layer Perspective Insights
        insights = structured_data.get("perspective_insights", {})
        if insights:
            lines.append("#### 専門戦術インサイト（理論適用と3層考察）")
            for key, item in insights.items():
                title = "試合の流れ・勝敗因果" if key == "game_flow" else ("プレッシングとビルドアップ" if key == "pressing_battle" else "交代策とマネジメント")
                lines.append(f"**《{title}》**")
                lines.append(f"- **現象要約**: {item.get('layer1_summary', '')}")
                lines.append(f"- **理論的根拠**: {item.get('layer3_theory', '')}")
                lines.append(f"- **相手視点**: {item.get('away_perspective', '')}")
                lines.append("")

        # Key Tactical Events
        events = structured_data.get("key_tactical_events", [])
        if events:
            lines.append("#### 勝敗の分岐点（Key Tactical Events）")
            for ev in events:
                m_min = ev.get("minute", "-")
                cat = ev.get("category", "")
                actors = ", ".join(ev.get("actors", []))
                zone = ev.get("zone", "")
                desc = ev.get("description", "")
                lines.append(f"- **{m_min}分 [{cat}]** ({zone} / 関与: {actors}): {desc}")
            lines.append("")

        return "\n".join(lines)

    def _format_deep_metrics_table(
        self,
        metrics: Dict[str, Any],
        home_name: str,
        away_name: str,
    ) -> str:
        """Render markdown table for deep metrics."""
        conv = metrics.get("conversion_rates", {})
        ft = metrics.get("field_tilt", {})

        h_conv = conv.get("home", {})
        a_conv = conv.get("away", {})

        h_ft = ft.get("home_field_tilt", 50.0)
        a_ft = ft.get("away_field_tilt", 50.0)

        lines: List[str] = [
            f"| 指標項目 | {home_name} | {away_name} |",
            "| :--- | :---: | :---: |",
            f"| 敵陣支配率 (Field Tilt) | {h_ft:.1f}% | {a_ft:.1f}% |",
            f"| 30mライン進入回数 | {h_conv.get('m30_count', '-')}回 | {a_conv.get('m30_count', '-')}回 |",
            f"| PA進入回数 (ボックス進入) | {h_conv.get('pa_count', '-')}回 | {a_conv.get('pa_count', '-')}回 |",
            f"| 進入変換率 (30m->PA) | {h_conv.get('rate_30_to_pa', 0):.1f}% | {a_conv.get('rate_30_to_pa', 0):.1f}% |",
            f"| 決定力変換率 (PA->シュート) | {h_conv.get('rate_pa_to_shot', 0):.1f}% | {a_conv.get('rate_pa_to_shot', 0):.1f}% |",
        ]
        return "\n".join(lines)

    # =========================================================================
    # Database and Data Loading Helpers
    # =========================================================================

    def _fetch_matches_for_team(self, team_id: str, season: int = 2026) -> List[Dict[str, Any]]:
        """Query DB for all matches involving a specific team."""
        conn = get_db_connection(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT match_id, season, matchweek, date, home_team_id, away_team_id,
                   home_score, away_score, stadium, weather, pitch_condition, attendance
            FROM matches
            WHERE (home_team_id = ? OR away_team_id = ?) AND season = ?
            ORDER BY date ASC, matchweek ASC;
            """,
            (team_id, team_id, season),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def _fetch_all_matches(self, season: int = 2026) -> List[Dict[str, Any]]:
        """Query DB for all matches in a season."""
        conn = get_db_connection(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT match_id, season, matchweek, date, home_team_id, away_team_id,
                   home_score, away_score, stadium, weather, pitch_condition, attendance
            FROM matches
            WHERE season = ?
            ORDER BY matchweek ASC, date ASC;
            """,
            (season,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    def _load_structured_json(self, match_id: str) -> Optional[Dict[str, Any]]:
        """Search and load structured tactical json file for match_id."""
        candidate = self.structured_dir / f"{match_id}_tactical.json"
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                pass

        for p in self.structured_dir.glob(f"*{match_id}*_tactical.json"):
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None


if __name__ == "__main__":
    exporter = NotebookLMExporter()
    files = exporter.export_all()
    print(f"\nSuccessfully generated {len(files)} documents for Google NotebookLM:")
    for f in files:
        print(f" - {f.name} ({f.stat().st_size:,} bytes)")
