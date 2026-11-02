"""tests/test_team_view.py

views/team_view.py の単体テスト (unittest)。
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import views.team_view as tv


class TestTeamView(unittest.TestCase):
    """Test suite for views/team_view.py module."""

    def test_imports_and_definitions(self):
        """主要なUI関数が定義されていること."""
        self.assertTrue(callable(tv.render_team_view))
        self.assertTrue(callable(tv._render_team_selector))
        self.assertTrue(callable(tv._render_club_header))
        self.assertTrue(callable(tv._render_tactical_profile_tab))
        self.assertTrue(callable(tv._render_squad_tab))
        self.assertTrue(callable(tv._render_h2h_tab))
        self.assertTrue(callable(tv._render_signature_metrics_section))
        self.assertTrue(callable(tv._render_tactical_radar_chart))
        self.assertTrue(callable(tv._render_win_loss_analysis_section))
        self.assertTrue(callable(tv._render_style_adherence_section))
        self.assertTrue(callable(tv._render_goal_and_time_dynamics_section))
        self.assertTrue(callable(tv._render_cross_analytics_section))
        self.assertTrue(callable(tv._render_55_metrics_expander_section))

    @patch("views.team_view.st")
    def test_render_team_selector(self, mock_st):
        """チームセレクターがselectboxを正しく呼ぶこと."""
        mock_st.session_state = {"selected_team_id": "FCT"}
        mock_st.columns.return_value = [MagicMock(), MagicMock()]
        mock_st.selectbox.return_value = "FCT"

        selected = tv._render_team_selector()
        self.assertEqual(selected, "FCT")
        mock_st.selectbox.assert_called_once()


if __name__ == "__main__":
    unittest.main()
