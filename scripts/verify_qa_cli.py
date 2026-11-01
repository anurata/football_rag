"""
scripts/verify_qa_cli.py

Local CLI interactive verification tool for TacticalQAEngine.
Enables rapid prompt engineering, RAG context inspection,
and Google Search Grounding testing in the local terminal.
"""

import argparse
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.gemini_client import GeminiTacticalClient
from agent.qa_engine import TacticalQAEngine


def run_qa_cli(
    question: str,
    match_id: str = None,
    enable_web_search: bool = False,
    mock_mode: bool = False,
) -> None:
    """Execute a single QA verification run and print structured results."""
    print("=" * 60)
    print("⚽ J-League Tactical QA Local Verification CLI")
    print(f"Match ID: {match_id or 'Global (All 2026 Season)'}")
    print(f"Web Search: {'ENABLED (Google Search)' if enable_web_search else 'DISABLED'}")
    print(f"Mock Mode: {mock_mode}")
    print(f"Question: {question}")
    print("=" * 60)

    client = GeminiTacticalClient(mock_mode=mock_mode)
    engine = TacticalQAEngine(gemini_client=client, mock_mode=mock_mode)

    res = engine.ask(
        question=question,
        match_id=match_id,
        enable_web_search=enable_web_search,
    )

    print("\n📋 【AI回答】\n")
    print(res.get("answer", ""))

    queries = res.get("web_search_queries", [])
    if queries:
        print("\n🔍 【実行されたWeb検索クエリ】:")
        for q in queries:
            print(f"  - {q}")

    sources = res.get("grounding_sources", [])
    if sources:
        print("\n🌐 【参照Webソース】:")
        for s in sources:
            print(f"  - {s.get('title')}: {s.get('url')}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Tactical QA CLI Verification")
    parser.add_argument(
        "--question",
        "-q",
        type=str,
        default="FC東京の基本戦術と直近の課題は何ですか？",
        help="Inquiry question to test",
    )
    parser.add_argument(
        "--match-id",
        "-m",
        type=str,
        default=None,
        help="Optional match_id to bind context",
    )
    parser.add_argument(
        "--search",
        "-s",
        action="store_true",
        help="Enable Google Search Grounding",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock mode without Gemini API key",
    )

    args = parser.parse_args()
    run_qa_cli(
        question=args.question,
        match_id=args.match_id,
        enable_web_search=args.search,
        mock_mode=args.mock,
    )


if __name__ == "__main__":
    main()
