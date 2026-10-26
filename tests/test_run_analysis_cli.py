"""
Unit tests for scripts/run_analysis.py CLI tool.
Validates one-shot command execution and prompt generation.
"""

import unittest
from pipeline.db import init_db
from agent.sql_tools import TacticalSQLTools
from agent.engine import TacticalAnalystEngine
from scripts.run_analysis import format_cli_output


class TestRunAnalysisCLI(unittest.TestCase):
    """Test suite for run_analysis CLI formatting and output."""

    def setUp(self):
        self.conn = init_db(":memory:")
        self.sql_tools = TacticalSQLTools(conn=self.conn)
        self.engine = TacticalAnalystEngine(sql_tools=self.sql_tools)

    def tearDown(self):
        self.sql_tools.close()
        if self.conn:
            self.conn.close()

    def test_watching_guide_cli_output(self):
        """Verify watching guide generation via engine and CLI formatting."""
        res = self.engine.build_watching_guide(
            match_id="20261021_FCT_KAS",
            formation_home="4-4-2",
            formation_away="3-4-2-1",
        )
        formatted = format_cli_output(res)
        self.assertIn("【Jリーグ戦術分析RAG エージェント出力】", formatted)
        self.assertIn("開始10分の「配置の答え合わせ」", formatted)
        self.assertIn("炭鉱のカナリア", formatted)

    def test_why_cli_output(self):
        """Verify why question prompt generation via engine and CLI formatting."""
        res = self.engine.build_why_analysis(
            match_id="20261021_FCT_KAS",
            team_id="FCT",
            phenomenon="後半の被xG増加",
        )
        formatted = format_cli_output(res)
        self.assertIn("消去法で真因を特定", formatted)
        self.assertIn("後半の被xG増加", formatted)

    def test_llm_response_formatting(self):
        """Verify format_cli_output includes LLM response when present."""
        res = {
            "system_prompt": "システム",
            "user_prompt": "ユーザーの質問",
            "response": "Gemini推論結果: 相手SBの裏を突くロングカウンターが奏功。",
        }
        formatted = format_cli_output(res)
        self.assertIn("■ LLM 推論回答:", formatted)
        self.assertIn("Gemini推論結果:", formatted)


if __name__ == "__main__":
    unittest.main()
