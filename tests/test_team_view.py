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
        self.assertTrue(callable(tv._inject_metric_table_custom_css))
        self.assertTrue(callable(tv._render_metric_row))
        self.assertTrue(callable(tv._render_metric_category_table))
        self.assertTrue(callable(tv._render_metric_dialog_body))
        self.assertTrue(callable(tv._show_metric_detail_dialog))

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
        mock_st.columns.side_effect = lambda spec, *args, **kwargs: [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]
        mock_st.expander.return_value.__enter__.return_value = MagicMock()
        mock_st.button.return_value = False

        tv._render_55_metrics_expander_section("FCT")
        mock_st.caption.assert_called()
        self.assertGreaterEqual(mock_st.expander.call_count, 6)

    @patch("views.team_view.st")
    def test_show_metric_detail_dialog(self, mock_st):
        """戦術指標詳細ダイアログが正しく要素を描画すること."""
        mock_st.columns.side_effect = lambda spec, *args, **kwargs: [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]
        mock_st.button.return_value = False

        sample_item = {
            "metric_name": "04_パス総数",
            "season_avg": 489.58,
            "rank": 7,
            "total_teams": 20,
            "best_val": 560.0,
            "best_team_name": "浦和",
            "league_avg": 455.43,
            "description": "ポゼッション維持とゲーム支配を司る基幹指標。",
            "current_tier": {
                "tier": 2,
                "stars": "★★★★☆",
                "level": "A (上位水準)",
            },
            "five_tier_scale": [
                {
                    "tier": 1,
                    "stars": "★★★★★",
                    "level": "S (リーグ屈指)",
                    "range": "520.00以上",
                    "description": "圧倒的なポゼッション",
                },
                {
                    "tier": 2,
                    "stars": "★★★★☆",
                    "level": "A (上位水準)",
                    "range": "480.00〜519.99",
                    "description": "優れたパス供給力",
                },
            ],
        }

        # _render_metric_dialog_body 実行
        tv._render_metric_dialog_body(sample_item)
        mock_st.subheader.assert_called_with("04_パス総数")
        mock_st.info.assert_called_with(sample_item["description"])

    @patch("views.team_view.st")
    def test_render_metric_row(self, mock_st):
        """指標行が2段カード形式（上段: 指標名+?+直近/平均、下段: バー）で正しく描画されること."""
        mock_st.columns.side_effect = lambda spec, *args, **kwargs: [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]
        mock_st.button.return_value = False

        sample_item = {
            "metric_name": "04_パス総数",
            "season_avg": 489.58,
            "rank": 7,
            "total_teams": 20,
            "latest_val": 540,
            "league_avg": 455.43,
            "current_tier": {
                "stars": "★★★☆☆",
                "level": "A (上位水準)",
            },
        }

        tv._render_metric_row(sample_item)
        # 上段の2カラム分割 + 指標名・ボタンの2カラム分割
        self.assertGreaterEqual(mock_st.columns.call_count, 2)
        # ?ボタンが描画されていること
        mock_st.button.assert_called_with("?", key="btn_help_04_パス総数", help="戦術指標の詳細解説と5段階判定基準をダイアログで表示")
        # バーセルHTMLおよびテキストを含むmarkdownが描画されていること
        self.assertGreaterEqual(mock_st.markdown.call_count, 3)

    def test_get_sorted_team_list(self):
        """順位順のチームリストが正常に取得できること."""
        teams = tv._get_sorted_team_list()
        self.assertIsInstance(teams, list)
        self.assertGreaterEqual(len(teams), 1)
        self.assertIn("team_id", teams[0])
        self.assertIn("rank", teams[0])
        self.assertIn("team_name", teams[0])

    @patch("views.team_view.st")
    def test_render_team_dialog_body(self, mock_st):
        """モバイル用クラブ選択モーダルが描画されること."""
        mock_st.columns.side_effect = lambda spec, *args, **kwargs: [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]
        mock_st.container.return_value.__enter__.return_value = MagicMock()
        mock_st.button.return_value = False

        sample_teams = [
            {"team_id": "FCT", "team_name": "FC東京", "rank": 1, "points": 10},
            {"team_id": "ZEL", "team_name": "町田", "rank": 2, "points": 9},
        ]
        tv._render_team_dialog_body(sample_teams, "FCT")
        mock_st.markdown.assert_called()

    @patch("views.team_view.st")
    def test_render_team_selector(self, mock_st):
        """レスポンシブなチームセレクター（PC横並び+モバイルダイアログ連携）が正しく描画されること."""
        mock_st.session_state = {"selected_team_id": "FCT"}
        mock_st.columns.side_effect = lambda spec, *args, **kwargs: [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]
        mock_st.button.return_value = False

        selected = tv._render_team_selector()
        self.assertEqual(selected, "FCT")
        mock_st.markdown.assert_called()

    def test_build_signature_metric_row_html(self):
        """チーム平均・リーグ平均・リーグ順位が1行HTMLとして正しく生成されること."""
        sample_item = {
            "metric_name": "46_ベイズ縮小決定力スキル",
            "team_value": 1.47,
            "league_average": 1.17,
            "rank": 1,
            "total_teams": 20,
            "z_score": 2.32,
        }
        html = tv._build_signature_metric_row_html(sample_item)
        self.assertIn("1.47", html)
        self.assertIn("1.17", html)
        self.assertIn("1位/20", html)
        self.assertIn("flex-wrap: nowrap", html)

    @patch("views.team_view.st")
    def test_render_signature_metric_card(self, mock_st):
        """シグネチャー指標カードが1行HTMLと丸い？ボタンを含めて正常に描画されること."""
        mock_st.container.return_value.__enter__.return_value = MagicMock()
        mock_st.columns.side_effect = lambda spec, *args, **kwargs: [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]
        mock_st.button.return_value = False

        sample_item = {
            "metric_name": "46_ベイズ縮小決定力スキル",
            "team_value": 1.47,
            "league_average": 1.17,
            "rank": 1,
            "total_teams": 20,
            "z_score": 2.32,
        }
        tv._render_signature_metric_card(sample_item, is_strength=True, team_id="FCT")
        # タイトルがインラインクラス付きHTMLで出力されていること
        md_calls = [c[0][0] for c in mock_st.markdown.call_args_list if c[0]]
        self.assertTrue(any("sig-metric-title" in s and "46_ベイズ縮小決定力スキル" in s for s in md_calls))
        mock_st.button.assert_called_with("?", key="btn_sig_help_46_ベイズ縮小決定力スキル", help="46_ベイズ縮小決定力スキルの詳細解説と判定基準をダイアログで表示")
        mock_st.caption.assert_called()

    def test_find_55_metric_detail(self):
        """55指標詳細検索ヘルパーが正常に指標データを取得できること."""
        item = tv._find_55_metric_detail("04_パス総数", "FCT")
        self.assertIsNotNone(item)
        self.assertEqual(item["metric_name"], "04_パス総数")
        self.assertIn("current_tier", item)


if __name__ == "__main__":
    unittest.main()
