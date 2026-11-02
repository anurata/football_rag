"""
tests/test_ai_modal.py

Unit tests for AI Modal helper logic and context injection.
"""

import unittest
import streamlit as st

from views.components.ai_modal import (
    build_session_key,
    _inject_context_prompt,
    get_ai_chat_store,
)


class TestAIModal(unittest.TestCase):
    """Test suite for AI modal components."""

    def setUp(self) -> None:
        for key in list(st.session_state.keys()):
            del st.session_state[key]

    def test_build_session_key(self) -> None:
        """Verify deterministic session key generation."""
        key = build_session_key(
            view_type="MATCH",
            section_key="ratings",
            match_id="2026102505",
            team_id="FCT",
        )
        self.assertEqual(key, "MATCH_m_2026102505_t_FCT_s_ratings")

        global_key = build_session_key(view_type="GLOBAL")
        self.assertEqual(global_key, "GLOBAL")

    def test_inject_context_prompt(self) -> None:
        """Verify context prefix generation for prompts."""
        context = {
            "section_key": "ratings",
            "team_id": "FCT",
            "player_name": "仲川 輝人",
            "note": "後半から途中出場",
        }
        res = _inject_context_prompt("採点の理由を教えて", context)
        self.assertIn("【注目セクション: ratings】", res)
        self.assertIn("【注目チーム: FCT】", res)
        self.assertIn("【注目選手: 仲川 輝人】", res)
        self.assertIn("【補足文脈: 後半から途中出場】", res)
        self.assertTrue(res.endswith("採点の理由を教えて"))

        empty_res = _inject_context_prompt("一般的な質問", {})
        self.assertEqual(empty_res, "一般的な質問")

    def test_get_ai_chat_store(self) -> None:
        """Verify session_state caching of store."""
        store1 = get_ai_chat_store()
        store2 = get_ai_chat_store()
        self.assertIs(store1, store2)


if __name__ == "__main__":
    unittest.main()

