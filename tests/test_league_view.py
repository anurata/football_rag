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

from views.league_view import (
    _render_form_badge,
    _render_team_report_mini_card,
    _render_match_pair_report_card,
)


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

    def test_render_team_report_mini_card_unique_keys(self):
        """Verify button key incorporates key_prefix to avoid duplicate element keys."""
        from unittest.mock import patch, MagicMock

        card = {
            "team_id": "KAS",
            "team_name": "鹿島アントラーズ",
            "rank": "A",
            "total_score": 52,
            "critique": {"headline": "圧倒", "text": "完勝"},
            "score": "2-0",
            "opp_team_name": "セレッソ大阪",
            "match_id": "20261031_KAS_CER",
            "metrics": {},
            "week_rank": 1,
        }

        with patch("views.league_view.st") as mock_st:
            mock_st.columns.side_effect = lambda spec: [MagicMock() for _ in (spec if isinstance(spec, list) else range(spec))]
            # 1. 異なる key_prefix で呼び出し
            _render_team_report_mini_card(card, show_rank_number=True, key_prefix="rank_0")
            _render_team_report_mini_card(card, show_rank_number=False, key_prefix="pair_h_20261031_KAS_CER")

            # st.button に渡された key 引数を検証
            button_calls = [call.kwargs.get("key") for call in mock_st.button.call_args_list]
            self.assertEqual(len(button_calls), 2)
            self.assertEqual(button_calls[0], "btn_rc_goto_rank_0_20261031_KAS_CER_KAS")
            self.assertEqual(button_calls[1], "btn_rc_goto_pair_h_20261031_KAS_CER_20261031_KAS_CER_KAS")
            self.assertNotEqual(button_calls[0], button_calls[1])

    def test_render_match_pair_report_card_unique_keys(self):
        """Verify match pair report card gives distinct prefixes to home and away."""
        from unittest.mock import patch, MagicMock

        pair = {
            "match_id": "20261031_KAS_CER",
            "date": "2026-10-31",
            "stadium": "カシマ",
            "home": {
                "team_id": "KAS",
                "team_name": "鹿島",
                "match_id": "20261031_KAS_CER",
            },
            "away": {
                "team_id": "CER",
                "team_name": "C大阪",
                "match_id": "20261031_KAS_CER",
            },
        }

        with patch("views.league_view.st") as mock_st:
            mock_st.columns.side_effect = lambda spec: [MagicMock() for _ in (spec if isinstance(spec, list) else range(spec))]
            _render_match_pair_report_card(pair)
            button_calls = [call.kwargs.get("key") for call in mock_st.button.call_args_list]
            self.assertEqual(len(button_calls), 2)
            self.assertIn("btn_rc_goto_pair_h_20261031_KAS_CER_20261031_KAS_CER_KAS", button_calls)
            self.assertIn("btn_rc_goto_pair_a_20261031_KAS_CER_20261031_KAS_CER_CER", button_calls)
            self.assertNotEqual(button_calls[0], button_calls[1])


if __name__ == "__main__":
    unittest.main()
