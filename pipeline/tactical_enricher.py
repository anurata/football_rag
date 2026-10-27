"""
AI-Powered High-Fidelity Tactical Enricher (pipeline/tactical_enricher.py).

Uses Gemini 3.8 Flash to transform raw match telemetry, deterministic deep metrics,
and live commentaries into professional tactical analysis matching Mito match quality.
Conforms to data_analysis_specification.md.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import logging
import re

from agent.gemini_client import GeminiTacticalClient
from scripts.calculate_deep_metrics import calculate_match_deep_metrics

logger = logging.getLogger("tactical_enricher")

TACTICAL_ANALYST_SYSTEM_PROMPT = """あなたはJリーグ専属のトッププロ戦術分析官です。
提供された公式生データ、事前計算された客観深層指標（進入変換率・CBP・速報カウント）、
時系列テキスト速報、および公式戦評・監督会見を照合し、
プロの分析官レベルの深い戦術的因果・駆け引き・アウェイ（対戦相手）視点を言語化した構造化JSONを作成してください。

【厳格な生成ルール（Zero-Hallucination & High-Fidelity）】
1. 固定の抽象定型文（「中盤のせめぎ合い」「ボランチの立ち位置を微修正」「リスクを抑えた前進」など）の出力は厳禁です。
2. 出場選手（背番号・実名）、途中交代選手、監督名を必ず名指しし、「誰が」「どこ（レーン・ハーフスペース・ポケット）で」「何をして」「相手の誰を釣り出し/防壁を破ったか」の力学を詳述してください。
3. 相手チーム（AWAY）視点を対等に論じ、相手が何を狙い、どこで守備が決壊し、どこに継続すべき光明があったかを論理的に分析してください。
4. 6フェーズ（0-15, 15-30, 30-45+, 45-60, 60-75, 75-90+）それぞれにおいて、実際のスコア動意、退場、交代、攻勢指数の波を反映した具体的推移を記述してください。
"""


def _load_raw_json(path: Path) -> Optional[Dict[str, Any]]:
    """Safely load JSON file."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to load JSON from %s: %e", path, e)
    return None


def _load_official_markdown(base_dir: Path, target_id: str) -> str:
    """Load official club review markdown if available."""
    md_dir = base_dir.parent / "markdown" / "2026"
    if not md_dir.exists():
        return ""
    for p in md_dir.glob(f"*{target_id}*.md"):
        try:
            return p.read_text(encoding="utf-8")[:3000]
        except Exception:
            pass
    return ""


class TacticalEnricher:
    """Enriches raw match data into high-fidelity tactical structures using Gemini."""

    def __init__(
        self,
        gemini_client: Optional[GeminiTacticalClient] = None,
        raw_dir: Optional[Path] = None,
        structured_dir: Optional[Path] = None,
    ):
        self.client = gemini_client or GeminiTacticalClient()
        self.raw_dir = raw_dir or Path(__file__).resolve().parent.parent / "data" / "raw"
        self.structured_dir = (
            structured_dir or Path(__file__).resolve().parent.parent / "data" / "structured"
        )
        self.structured_dir.mkdir(parents=True, exist_ok=True)

    def build_enrichment_prompt(
        self,
        target_id: str,
        metrics: Dict[str, Any],
        raw_context: Dict[str, Any],
    ) -> str:
        """Construct a comprehensive prompt feeding all deterministic stats and text."""
        home_name = raw_context.get("home_team", "FC東京")
        away_name = raw_context.get("away_team", "AWAY")
        score = raw_context.get("score", "0-0")
        report_text = raw_context.get("report_text", "")
        coach_h = raw_context.get("coach_home", "監督")
        coach_a = raw_context.get("coach_away", "監督")

        cr = metrics.get("conversion_rates", {})
        ft = metrics.get("field_tilt", {})
        cbp = metrics.get("cbp_rankings", {})
        ev = metrics.get("timeline_events", {})

        prompt_lines = [
            f"# J1公式試合戦術推論タスク: {home_name} vs {away_name} (スコア: {score})",
            f"対象ID: {target_id}",
            f"両軍監督: {home_name}【{coach_h}】 vs {away_name}【{coach_a}】",
            "",
            "## 【1. 客観深層指標（決定論的算出値）】",
            f"- 敵陣支配度 (Field Tilt): {home_name} {ft.get('home_field_tilt')}% ({ft.get('home_eval')}) vs {away_name} {ft.get('away_field_tilt')}% ({ft.get('away_eval')})",
            f"- 進入変換率 (30m→PA): {home_name} {cr.get('home', {}).get('rate_30_to_pa')}% ({cr.get('home', {}).get('eval_30_to_pa')}) vs {away_name} {cr.get('away', {}).get('rate_30_to_pa')}%",
            f"- 決定力変換率 (PA→シュート): {home_name} {cr.get('home', {}).get('rate_pa_to_shot')}% ({cr.get('home', {}).get('eval_pa_to_shot')}) vs {away_name} {cr.get('away', {}).get('rate_pa_to_shot')}%",
            f"- 途中交代枠インパクト: {home_name} CBP {cbp.get('home', {}).get('bench_impact')} ({cbp.get('home', {}).get('bench_eval')}) vs {away_name} CBP {cbp.get('away', {}).get('bench_impact')}",
            f"- 速報事象集計: 総事象 {ev.get('total_events')}件 / {home_name} シュート{ev.get('home_counts', {}).get('shots')}本, CK{ev.get('home_counts', {}).get('corners')}, 退場{ev.get('home_counts', {}).get('red_cards')} / {away_name} シュート{ev.get('away_counts', {}).get('shots')}本, CK{ev.get('away_counts', {}).get('corners')}, 退場{ev.get('away_counts', {}).get('red_cards')}",
            "",
            "## 【2. 主要キーマン (CBP Top 3)】",
            f"- {home_name} 攻撃CBP上位: {json.dumps(cbp.get('home', {}).get('top_attack', []), ensure_ascii=False)}",
            f"- {home_name} 守備/奪取CBP上位: {json.dumps(cbp.get('home', {}).get('top_gain', []), ensure_ascii=False)}",
            f"- {away_name} 攻撃CBP上位: {json.dumps(cbp.get('away', {}).get('top_attack', []), ensure_ascii=False)}",
            f"- {away_name} 守備/奪取CBP上位: {json.dumps(cbp.get('away', {}).get('top_gain', []), ensure_ascii=False)}",
            "",
            "## 【3. 公式戦評・ダイジェスト】",
            report_text[:1200] if report_text else "（戦評テキストなし）",
            "",
            "## 【4. 速報重要プレー・得点・退場イベント】",
            "\n".join([f"- {kp}" for kp in ev.get("key_plays_sample", [])]),
            "",
            "## 【出力形式要件】",
            "必ず以下のキー構造を持つ単一の純粋なJSONオブジェクトのみを出力してください（Markdownの ```json 等の囲みを含めても可）：",
            """{
  "match_id": "%s",
  "home_formation": "4-2-1-3 または 4-4-2 等",
  "away_formation": "4-4-2 または 3-4-2-1 等",
  "tactical_highlights": [
    "勝敗を分けた具体的戦術ハイライト1（選手名・エリア・因果明記）",
    "勝敗を分けた具体的戦術ハイライト2",
    "勝敗を分けた具体的戦術ハイライト3"
  ],
  "phases": [
    {
      "phase": "0-15",
      "dominant_team": "HOME または AWAY または EQUAL",
      "momentum_summary": "0-15分の主導権・好機創出・スコア動向の生きた戦術記述",
      "pressing_battle": "前線ハイプレスとビルドアップ前進の噛み合わせ・プレス回避",
      "tactical_adjustments": "監督の指示・ポジショニングの微調整・立ち位置の修正"
    },
    { "phase": "15-30", ... },
    { "phase": "30-45+", ... },
    { "phase": "45-60", ... },
    { "phase": "60-75", ... },
    { "phase": "75-90+", ... }
  ],
  "key_tactical_events": [
    {
      "minute": 15,
      "period": "1H",
      "team_side": "HOME または AWAY",
      "category": "CHANCE_CREATION または PRESSING または SUBSTITUTION_TACTIC",
      "actors": ["選手名1", "選手名2"],
      "zone": "右ポケット または ペナルティエリア中央 等",
      "description": "局面の具体的戦術解説"
    }
  ],
  "perspective_insights": {
    "game_flow": {
      "layer1_summary": "数値の背景とピッチ上の示唆（350文字以上）",
      "layer3_theory": "戦術理論（ポジショナルプレー等）に基づく構造的解釈",
      "away_perspective": "アウェイチーム視点の対等分析（250文字以上）"
    },
    "pressing_battle": {
      "layer1_summary": "プレスの強度と噛み合わせの示唆",
      "layer3_theory": "ハイプレスと回避理論",
      "away_perspective": "アウェイチームのプレッシング・ブロック視点"
    },
    "substitution_impact": {
      "layer1_summary": "交代策による強度と配置の変化",
      "layer3_theory": "5人交代制マネジメント論",
      "away_perspective": "アウェイチームのベンチワーク成否"
    }
  }
}"""
            % target_id,
        ]

        return "\n".join(prompt_lines)

    def extract_tactical_structure(
        self,
        target_id: str,
        match_id_synonym: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run Gemini enrichment pipeline for a single match and return enriched dict.
        """
        metrics = calculate_match_deep_metrics(target_id, base_dir=self.raw_dir)

        # Load raw contexts
        fl_path = None
        yahoo_stat_path = None
        for p in (self.raw_dir / "football_lab").glob(f"*{target_id}*.json"):
            fl_path = p
            break
        for p in (self.raw_dir / "yahoo").glob(f"*{target_id}*_stats.json"):
            yahoo_stat_path = p
            break

        fl_data = _load_raw_json(fl_path) if fl_path else {}
        yahoo_stat = _load_raw_json(yahoo_stat_path) if yahoo_stat_path else {}

        raw_context = {
            "home_team": yahoo_stat.get("match_info", {}).get("home_team", "FC東京"),
            "away_team": yahoo_stat.get("match_info", {}).get("away_team", "AWAY"),
            "score": yahoo_stat.get("match_info", {}).get("score", "0-0"),
            "report_text": fl_data.get("data", {}).get("report_text", ""),
            "coach_home": fl_data.get("data", {}).get("players", {}).get("home", {}).get("coach", "松橋 力蔵"),
            "coach_away": fl_data.get("data", {}).get("players", {}).get("away", {}).get("coach", "監督"),
        }

        user_prompt = self.build_enrichment_prompt(target_id, metrics, raw_context)
        raw_response = self.client.generate(
            system_prompt=TACTICAL_ANALYST_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
        )

        cleaned_json = self._clean_json_string(raw_response)
        parsed = json.loads(cleaned_json)

        # Merge precalculated deep metrics
        parsed["deep_metrics"] = metrics

        # Save to both target_id and match_id_synonym
        self._save_structured(parsed, target_id)
        if match_id_synonym:
            parsed_syn = dict(parsed)
            parsed_syn["match_id"] = match_id_synonym
            self._save_structured(parsed_syn, match_id_synonym)

        return parsed

    def _clean_json_string(self, text: str) -> str:
        """Strip markdown fences and whitespace from Gemini response."""
        text = text.strip()
        if "```json" in text:
            m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if m:
                return m.group(1).strip()
        elif "```" in text:
            m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
            if m:
                return m.group(1).strip()
        return text

    def _save_structured(self, data: Dict[str, Any], file_stem: str) -> None:
        """Save structured tactical data to JSON."""
        out_path = self.structured_dir / f"{file_stem}_tactical.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved high-fidelity tactical tactics to %s", out_path)
