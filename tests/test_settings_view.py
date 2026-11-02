"""
tests/test_settings_view.py

Unit tests for views/settings_view.py configuration and state persistence.
"""

import unittest
import streamlit as st

from views.settings_view import (
    init_settings_state,
    get_configured_gemini_client,
    get_default_api_key,
    render_settings_view,
)
from agent.gemini_client import DEFAULT_GEMINI_MODEL


class TestSettingsView(unittest.TestCase):
    """Test suite for Settings view logic and client configuration."""

    def setUp(self) -> None:
        for key in list(st.session_state.keys()):
            del st.session_state[key]

    def test_init_settings_state(self) -> None:
        """Verify default keys are populated in session state."""
        init_settings_state()
        self.assertIn("llm_api_key", st.session_state)
        self.assertIn("llm_model_name", st.session_state)
        self.assertIn("llm_mock_mode", st.session_state)
        self.assertEqual(st.session_state["llm_model_name"], DEFAULT_GEMINI_MODEL)
        self.assertFalse(st.session_state["llm_mock_mode"])

    def test_get_configured_gemini_client_defaults(self) -> None:
        """Verify client creation from initial state."""
        client = get_configured_gemini_client()
        self.assertEqual(client.model, DEFAULT_GEMINI_MODEL)
        self.assertFalse(client.mock_mode)

    def test_get_configured_gemini_client_custom_state(self) -> None:
        """Verify client picks up customized session state values."""
        st.session_state["llm_api_key"] = "test_custom_api_key_12345"
        st.session_state["llm_model_name"] = "gemini-2.5-pro"
        st.session_state["llm_mock_mode"] = True

        client = get_configured_gemini_client()
        self.assertEqual(client.api_key, "test_custom_api_key_12345")
        self.assertEqual(client.model, "gemini-2.5-pro")
        self.assertTrue(client.mock_mode)

    def test_render_settings_view_smoke(self) -> None:
        """Smoke test verifying render_settings_view runs without uncaught exceptions."""
        try:
            render_settings_view()
        except Exception as e:
            self.fail(f"render_settings_view() raised an unexpected exception: {e}")


if __name__ == "__main__":
    unittest.main()
