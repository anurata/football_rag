"""
Unit tests for GeminiTacticalClient (tests/test_gemini_client.py).
"""

import unittest
from unittest.mock import MagicMock, patch

from agent.gemini_client import GeminiTacticalClient


class TestGeminiTacticalClient(unittest.TestCase):
    def test_missing_api_key_returns_guidance(self):
        client = GeminiTacticalClient(api_key=None, mock_mode=False)
        # Clear any environment variables in this test instance
        client.api_key = None
        client._client = None

        res = client.generate(
            system_prompt="system",
            user_prompt="user",
        )
        self.assertIn("エラー: Gemini APIキーが未設定です", res)

    def test_mock_mode_generation(self):
        client = GeminiTacticalClient(mock_mode=True)
        self.assertTrue(client.is_available())

        res = client.generate(
            system_prompt="system",
            user_prompt="ユーザーの質問",
        )
        self.assertIn("プロ分析官の戦術推論レポート", res)
        self.assertIn("Why", res)
        self.assertIn("How", res)

    def test_as_callable_interface(self):
        client = GeminiTacticalClient(mock_mode=True)
        llm_fn = client.as_callable()

        res = llm_fn("システム", "プロンプト")
        self.assertIsInstance(res, str)
        self.assertTrue(len(res) > 0)

    @patch("agent.gemini_client.HAS_GENAI_SDK", True)
    def test_mocked_genai_call(self):
        mock_genai_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "AI戦術分析結果テキスト"
        mock_genai_client.models.generate_content.return_value = mock_response

        client = GeminiTacticalClient(api_key="dummy_key", mock_mode=False)
        client._client = mock_genai_client

        output = client.generate(
            system_prompt="システムプロンプト",
            user_prompt="後半の守備修正について",
        )
        self.assertEqual(output, "AI戦術分析結果テキスト")
        mock_genai_client.models.generate_content.assert_called_once()


if __name__ == "__main__":
    unittest.main()
