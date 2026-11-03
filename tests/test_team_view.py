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
        self.assertTrue(callable(tv._build_metric_rank_badge_style))
        self.assertTrue(callable(tv._build_metric_bar_cell_html))
        self.assertTrue(callable(tv._render_metric_row))
        self.assertTrue(callable(tv._render_metric_category_table))

    def test_build_metric_rank_badge_style(self):
        """順位に応じたバッジ色分けスタイルの検証."""
        bg1, text1 = tv._build_metric_rank_badge_style(1)
        self.assertEqual(bg1, "#fef3c7")
        self.assertEqual(text1, "#b45309")

        bg3, text3 = tv._build_metric_rank_badge_style(3)
        self.assertEqual(bg3, "#e0e7ff")
        self.assertEqual(text3, "#3730a3")

        bg15, text15 = tv._build_metric_rank_badge_style(15)
        self.assertEqual(bg15, "#f8fafc")
        self.assertEqual(text15, "#64748b")

    def test_build_metric_bar_cell_html(self):
        """インセルバーHTML生成ロジックの検証."""
        sample_item = {
            "metric_name": "20b_スプリント回数",
            "season_avg": 138.4,
            "rank": 1,
            "total_teams": 20,
            "bar_ratio": 100.0,
            "best_val": 138.4,
            "best_team_name": "FC東京",
        }
        html = tv._build_metric_bar_cell_html(sample_item)
        self.assertIn("138.4", html)
        self.assertIn("width: 100.0%", html)
        self.assertIn("1位/20", html)
        self.assertIn("linear-gradient", html)

    @patch("views.team_view.st")
    def test_render_55_metrics_expander_section(self, mock_st):
        """全55戦術指標セクションがエラーなく描画されること."""
        mock_st.columns.side_effect = lambda spec: [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]
        mock_st.expander.return_value.__enter__.return_value = MagicMock()
        mock_st.popover.return_value.__enter__.return_value = MagicMock()

        tv._render_55_metrics_expander_section("FCT")
        mock_st.caption.assert_called()
        self.assertGreaterEqual(mock_st.expander.call_count, 6)

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
