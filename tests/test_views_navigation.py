"""
tests/test_views_navigation.py

Unit tests for views/navigation.py deep-linking and session state management.
"""

import unittest
import streamlit as st

from views.navigation import (
    VIEW_LEAGUE,
    VIEW_TEAM,
    VIEW_MATCH,
    VIEW_PLAYER,
    VIEW_AI_CHAT,
    VIEW_SETTINGS,
    VIEW_LABELS,
    LABEL_TO_VIEW,
    init_navigation_state,
    get_current_view,
    navigate_to,
)


class TestViewsNavigation(unittest.TestCase):
    """Test suite for navigation state and deep-linking functions."""

    def setUp(self) -> None:
        # Clear or reset st.session_state
        for key in list(st.session_state.keys()):
            del st.session_state[key]

    def test_constants_consistency(self) -> None:
        """Verify view constants and their label mappings."""
        expected_views = [
            VIEW_LEAGUE,
            VIEW_TEAM,
            VIEW_MATCH,
            VIEW_PLAYER,
            VIEW_AI_CHAT,
            VIEW_SETTINGS,
        ]
        for v in expected_views:
            self.assertIn(v, VIEW_LABELS)
            label = VIEW_LABELS[v]
            self.assertEqual(LABEL_TO_VIEW[label], v)

    def test_init_navigation_state_defaults(self) -> None:
        """Verify default state initialization."""
        init_navigation_state(default_view=VIEW_MATCH)
        self.assertEqual(st.session_state["current_view"], VIEW_MATCH)
        self.assertIsNone(st.session_state["selected_match_id"])
        self.assertFalse(st.session_state["auto_open_ai_modal"])

    def test_get_current_view(self) -> None:
        """Verify getting the current active view."""
        self.assertEqual(get_current_view(), VIEW_TEAM)
        st.session_state["current_view"] = VIEW_MATCH
        self.assertEqual(get_current_view(), VIEW_MATCH)

    def test_sidebar_radio_sync(self) -> None:
        """Verify sidebar_view_radio synchronizes properly on navigate_to."""
        navigate_to(view=VIEW_TEAM, trigger_rerun=False)
        self.assertEqual(st.session_state["sidebar_view_radio"], VIEW_LABELS[VIEW_TEAM])

        navigate_to(view=VIEW_MATCH, trigger_rerun=False)
        self.assertEqual(st.session_state["sidebar_view_radio"], VIEW_LABELS[VIEW_MATCH])

    def test_navigate_to_deep_linking(self) -> None:
        """Verify navigate_to sets all context attributes properly."""
        navigate_to(
            view=VIEW_MATCH,
            match_id="2026102505",
            team_id="FCT",
            section_key="ratings",
            resume_session_id="session_123",
            auto_open_ai=True,
            trigger_rerun=False,
        )
        self.assertEqual(st.session_state["current_view"], VIEW_MATCH)
        self.assertEqual(st.session_state["selected_match_id"], "2026102505")
        self.assertEqual(st.session_state["selected_team_id"], "FCT")
        self.assertEqual(st.session_state["selected_section_key"], "ratings")
        self.assertEqual(st.session_state["resume_session_id"], "session_123")
        self.assertTrue(st.session_state["auto_open_ai_modal"])

    def test_navigate_to_player(self) -> None:
        """Verify navigation to player view with player attributes."""
        navigate_to(
            view=VIEW_PLAYER,
            team_id="FCT",
            player_id="P999",
            player_name="仲川 輝人",
            trigger_rerun=False,
        )
        self.assertEqual(st.session_state["current_view"], VIEW_PLAYER)
        self.assertEqual(st.session_state["selected_team_id"], "FCT")
        self.assertEqual(st.session_state["selected_player_id"], "P999")
        self.assertEqual(st.session_state["selected_player_name"], "仲川 輝人")

    def test_navigate_to_settings(self) -> None:
        """Verify navigation to settings view."""
        navigate_to(
            view=VIEW_SETTINGS,
            trigger_rerun=False,
        )
        self.assertEqual(st.session_state["current_view"], VIEW_SETTINGS)

    def test_on_sidebar_nav_change_callback(self) -> None:
        """Verify _on_sidebar_nav_change updates current_view properly."""
        from views.navigation import _on_sidebar_nav_change
        init_navigation_state(VIEW_TEAM)
        st.session_state["sidebar_view_radio"] = VIEW_LABELS[VIEW_LEAGUE]
        _on_sidebar_nav_change()
        self.assertEqual(st.session_state["current_view"], VIEW_LEAGUE)

        st.session_state["sidebar_view_radio"] = VIEW_LABELS[VIEW_TEAM]
        _on_sidebar_nav_change()
        self.assertEqual(st.session_state["current_view"], VIEW_TEAM)


if __name__ == "__main__":
    unittest.main()
