"""
Interactive and one-shot CLI tool for tactical reasoning and watching guide generation.
Usage:
  python scripts/run_analysis.py --match-id 20261021_FCT_KAS --question why --query "後半の被xG増加の要因"
  python scripts/run_analysis.py --match-id 20261021_FCT_KAS --question watching_guide
  python scripts/run_analysis.py --interactive
"""

import os
import sys
import argparse
from pathlib import Path

# Add project root to sys.path so scripts can be run directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Optional, Dict, Any

from pipeline.db import DEFAULT_DB_PATH
from pipeline.vector_indexer import DEFAULT_CHROMA_DIR
from agent.engine import TacticalAnalystEngine
from agent.gemini_client import GeminiTacticalClient, DEFAULT_GEMINI_MODEL


def format_cli_output(result: Dict[str, Any]) -> str:
    """Format prompt and context output nicely for terminal display."""
    lines = [
        "=" * 70,
        "【Jリーグ戦術分析RAG エージェント出力】",
        "=" * 70,
        "",
        "■ システムプロンプト:",
        result.get("system_prompt", "").strip(),
        "",
        "-" * 70,
        "■ 生成された分析プロンプト (コンテキスト注入済み):",
        result.get("user_prompt", "").strip(),
        "",
        "=" * 70,
    ]
    if result.get("response"):
        lines.extend([
            "■ LLM 推論回答:",
            result.get("response", "").strip(),
            "=" * 70,
        ])
    return "\n".join(lines)


def run_interactive_mode(
    engine: TacticalAnalystEngine,
    client: Optional[GeminiTacticalClient] = None,
) -> None:
    """Guided interactive CLI session for coaches, analysts, and fans."""
    print("\n" + "=" * 60)
    print("  Jリーグ戦術分析・観戦ガイドRAG インタラクティブ分析")
    print("=" * 60)

    # 1. Ask for match ID
    match_id = input("\n[1] 分析対象の試合IDを入力してください (例: 20240223_HIR_URA): ").strip()
    if not match_id:
        match_id = "20240223_HIR_URA"
        print(f" -> デフォルト試合IDを使用: {match_id}")

    # 2. Select Question
    print("\n[2] 分析したい「問い」または「観戦ガイド」を選択してください:")
    print("  1. 【要因分析 (Why)】特定現象の要因をデータと消去法で特定")
    print("  2. 【改善処方箋 (How)】ボトルネックの構造的・属人的解決策")
    print("  3. 【反実仮想 (What-if)】戦術変更シミュレーション（光と影）")
    print("  4. 【陰のMVP (Unsung Hero)】特定選手のOn/Off影響度分析")
    print("  5. 【相性・ケミストリー】2選手の同時出場時スタッツ・距離感")
    print("  6. 【体質診断 (Game State)】先制時・同点時のチームDNA診断")
    print("  7. 【観戦が10倍面白くなる4つのレンズ】（観戦ガイド生成）")

    choice = input("\n選択番号 (1-7) [デフォルト 7]: ").strip() or "7"

    if choice == "1":
        query = input("分析したい現象を入力 (例: 後半の被xG増加とロスト急増): ").strip() or "敵陣パス成功率低下"
        res = engine.build_why_analysis(match_id=match_id, team_id="FCT", phenomenon=query)
    elif choice == "2":
        query = input("改善したいボトルネックを入力 (例: ハイプレス突破後のDF裏スペース被弾): ").strip() or "ハイプレス突破後の被弾"
        res = engine.build_how_analysis(team_id="FCT", bottleneck=query, formation_a="4-4-2", formation_b="3-4-2-1")
    elif choice == "3":
        query = input("試行したい戦術変更を入力 (例: SBを内側に絞らせる偽SB化): ").strip() or "SBを内側に絞らせる偽SB化"
        res = engine.build_what_if_analysis(opponent_team_id="KAS", tactical_change=query, formation_a="4-4-2", formation_b="3-4-2-1")
    elif choice == "4":
        pname = input("分析対象の選手名を入力 (例: 小泉 慶): ").strip() or "小泉 慶"
        res = engine.build_unsung_hero_analysis(team_id="FCT", player_name=pname)
    elif choice == "5":
        p_a = input("選手Aの名前 (例: 小泉 慶): ").strip() or "小泉 慶"
        p_b = input("選手Bの名前 (例: 荒木 遼太郎): ").strip() or "荒木 遼太郎"
        res = engine.build_chemistry_analysis(team_id="FCT", player_a=p_a, player_b=p_b)
    elif choice == "6":
        res = engine.build_game_state_dna_analysis(team_id="FCT", match_id=match_id)
    else:
        res = engine.build_watching_guide(match_id=match_id, formation_home="4-4-2", formation_away="3-4-2-1")

    if client and client.is_available():
        print("\nGemini API による推論を実行中...")
        res = engine.run_analysis(res, llm_callable=client.as_callable())

    print("\n" + format_cli_output(res))


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(description="J-League Tactical Analysis Agent CLI")
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Launch interactive terminal wizard",
    )
    parser.add_argument(
        "--match-id",
        type=str,
        default="20261021_FCT_KAS",
        help="Match ID to analyze",
    )
    parser.add_argument(
        "--team-id",
        type=str,
        default="FCT",
        help="Focus team normalized ID",
    )
    parser.add_argument(
        "--question", "-q",
        type=str,
        choices=["why", "how", "what_if", "unsung_hero", "chemistry", "game_state", "watching_guide"],
        default="watching_guide",
        help="Analysis question type",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="敵陣パス成功率低下",
        help="Phenomenon, bottleneck, or tactical change query string",
    )
    parser.add_argument(
        "--player",
        type=str,
        default="小泉 慶",
        help="Player name for unsung hero analysis",
    )
    parser.add_argument(
        "--player-b",
        type=str,
        default="荒木 遼太郎",
        help="Second player name for pairing chemistry",
    )
    parser.add_argument(
        "--formation-home",
        type=str,
        default="4-4-2",
        help="Home team formation",
    )
    parser.add_argument(
        "--formation-away",
        type=str,
        default="3-4-2-1",
        help="Away team formation",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output markdown file path",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )
    parser.add_argument(
        "--chroma-dir",
        type=str,
        default=DEFAULT_CHROMA_DIR,
        help="ChromaDB directory path",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        default=True,
        help="Execute LLM reasoning via Gemini API (default: True)",
    )
    parser.add_argument(
        "--no-llm",
        dest="llm",
        action="store_false",
        help="Disable LLM generation (print prompt only)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_GEMINI_MODEL,
        help=f"Gemini model identifier (default: {DEFAULT_GEMINI_MODEL})",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Explicit Gemini API key",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Use mock LLM generator for testing without API key",
    )

    args = parser.parse_args()

    engine = TacticalAnalystEngine()
    gemini_client = GeminiTacticalClient(
        api_key=args.api_key,
        model=args.model,
        mock_mode=args.mock,
    )

    if args.interactive:
        run_interactive_mode(engine, client=gemini_client if args.llm else None)
        return

    # One-shot CLI execution
    q = args.question
    if q == "why":
        res = engine.build_why_analysis(
            match_id=args.match_id,
            team_id=args.team_id,
            phenomenon=args.query,
        )
    elif q == "how":
        res = engine.build_how_analysis(
            team_id=args.team_id,
            bottleneck=args.query,
            formation_a=args.formation_home,
            formation_b=args.formation_away,
        )
    elif q == "what_if":
        res = engine.build_what_if_analysis(
            opponent_team_id="KAS",
            tactical_change=args.query,
            formation_a=args.formation_home,
            formation_b=args.formation_away,
        )
    elif q == "unsung_hero":
        res = engine.build_unsung_hero_analysis(
            team_id=args.team_id,
            player_name=args.player,
        )
    elif q == "chemistry":
        res = engine.build_chemistry_analysis(
            team_id=args.team_id,
            player_a=args.player,
            player_b=args.player_b,
        )
    elif q == "game_state":
        res = engine.build_game_state_dna_analysis(
            team_id=args.team_id,
            match_id=args.match_id,
        )
    else:  # watching_guide
        res = engine.build_watching_guide(
            match_id=args.match_id,
            formation_home=args.formation_home,
            formation_away=args.formation_away,
        )

    # Execute LLM generation if enabled
    if args.llm and gemini_client.is_available():
        res = engine.run_analysis(res, llm_callable=gemini_client.as_callable())

    output_text = format_cli_output(res)
    print(output_text)

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"\n[Saved to {args.output}]")


if __name__ == "__main__":
    main()
