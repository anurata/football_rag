"""
tests/test_league_view.py

Tests for views/league_view.py helper functions and logic.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Add root directory to path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from views.league_view import _render_form_badge


class TestLeagueView(unittest.TestCase):
    """Test suite for league_view UI helpers."""

    def test_render_form_badge(self):
        """Test form badge markdown formatting."""
        badge_empty = _render_form_badge([])
        self.assertEqual(badge_empty, "―")

        badge_wins = _render_form_badge(["W", "W", "W"])
        self.assertIn("🟢勝", badge_wins)

        badge_mixed = _render_form_badge(["W", "D", "L"])
        self.assertIn("🟢勝", badge_mixed)
        self.assertIn("⚪分", badge_mixed)
        self.assertIn("🔴負", badge_mixed)


if __name__ == "__main__":
    unittest.main()
