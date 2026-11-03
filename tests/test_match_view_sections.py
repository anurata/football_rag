"""
tests/test_match_view_sections.py

Unit tests for 5-section components in Match Deep Dive view.
"""

import unittest
from unittest.mock import MagicMock, patch

from views.components.match.summary_section import render_match_summary_section
from views.components.match.ratings_section import render_match_ratings_section
from views.components.match.analytics_section import render_match_analytics_section
from views.components.match.insights_section import render_match_insights_section
from views.components.match.player_stats_section import render_match_player_stats_section


class TestMatchViewSections(unittest.TestCase):
    def setUp(self):
        self.mock_qa = MagicMock()
        self.mock_rater = MagicMock()
        self.mock_rater.generate_match_ratings.return_value = {
            "mom": {
                "player_name": "仲川 輝人",
                "team_id": "FCT",
                "rating": 7.5,
                "reason": "決勝点演出",
            },
            "home_players": [
                {"number": 7, "name": "仲川 輝人", "position": "FW", "minutes": 80, "rating": "7.5", "comment": "好調"},
            ],
            "away_players": [
                {"number": 10, "name": "相手選手", "position": "MF", "minutes": 90, "rating": "6.0", "comment": "奮闘"},
            ],
            "coaches": {
                "home_coach": {"name": "ピーター クラモフスキー", "rating": "6.5", "comment": "交代的中"},
                "away_coach": {"name": "黒田 剛", "rating": "6.0", "comment": "手堅い采配"},
            },
        }

        self.mock_profiler = MagicMock()
        self.mock_profiler.analyze_win_loss_dynamics.return_value = {
            "home_team": {"team_id": "FCT", "outcome": "WIN", "reasons": ["先制点"], "improvements": ["終盤"]},
            "away_team": {"team_id": "ZEL", "outcome": "LOSS", "reasons": ["失点"], "improvements": ["前進"]},
        }
        self.mock_profiler.build_15_perspective_report.return_value = {
            "overall_structure_summary": {"title": "テストサマリー", "narrative": "テスト本文", "phases": []},
            "perspectives": [],
        }

        self.mock_comparator = MagicMock()
        self.mock_comparator.compare_facts_with_reviews.return_value = {
            "alignments": [{"topic": "プレス", "fact": "PPDA 8.4", "verdict": "合致", "statements": []}],
            "perception_gaps": [],
            "hidden_truths": [],
        }

        self.sample_summary = {
            "match": {"match_id": "2026080802", "home_team_id": "FCT", "away_team_id": "ZEL"},
            "home_possession": 55.0,
            "away_possession": 45.0,
            "home_shots": 12,
            "away_shots": 8,
        }

    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.subheader")
    @patch("streamlit.caption")
    @patch("streamlit.divider")
    def test_render_summary_section(self, mock_div, mock_cap, mock_sub, mock_md, mock_cols):
        mock_col = MagicMock()
        mock_cols.return_value = [mock_col, mock_col]
        render_match_summary_section(
            match_id="2026080802",
            home_id="FCT",
            away_id="ZEL",
            struct_summary={"title": "テスト", "narrative": "本文", "phases": []},
            qa_engine=self.mock_qa,
        )
        mock_sub.assert_called()

    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.subheader")
    @patch("streamlit.caption")
    @patch("streamlit.divider")
    def test_render_ratings_section(self, mock_div, mock_cap, mock_sub, mock_md, mock_cols):
        mock_col = MagicMock()
        mock_cols.return_value = [mock_col, mock_col]
        render_match_ratings_section(
            match_id="2026080802",
            home_id="FCT",
            away_id="ZEL",
            rater=self.mock_rater,
            summary=self.sample_summary,
            qa_engine=self.mock_qa,
        )
        mock_sub.assert_called()

    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.subheader")
    @patch("streamlit.caption")
    @patch("streamlit.divider")
    @patch("streamlit.plotly_chart")
    def test_render_analytics_section(self, mock_chart, mock_div, mock_cap, mock_sub, mock_md, mock_cols):
        mock_col = MagicMock()
        mock_cols.return_value = [mock_col, mock_col]
        render_match_analytics_section(
            match_id="2026080802",
            home_id="FCT",
            away_id="ZEL",
            profiler=self.mock_profiler,
            summary=self.sample_summary,
            qa_engine=self.mock_qa,
        )
        mock_sub.assert_called()

    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.subheader")
    @patch("streamlit.caption")
    @patch("streamlit.divider")
    def test_render_insights_section(self, mock_div, mock_cap, mock_sub, mock_md, mock_cols):
        mock_col = MagicMock()
        mock_cols.return_value = [mock_col, mock_col]
        render_match_insights_section(
            match_id="2026080802",
            home_id="FCT",
            away_id="ZEL",
            comparator=self.mock_comparator,
            profiler=self.mock_profiler,
            summary=self.sample_summary,
            reviews=[],
            qa_engine=self.mock_qa,
        )
        mock_sub.assert_called()

    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.subheader")
    @patch("streamlit.caption")
    @patch("streamlit.selectbox")
    @patch("streamlit.radio")
    def test_render_player_stats_section(self, mock_radio, mock_select, mock_cap, mock_sub, mock_md, mock_cols):
        mock_col = MagicMock()
        mock_cols.return_value = [mock_col, mock_col]
        mock_select.return_value = "cbp_total"
        mock_radio.return_value = "両チーム"
        render_match_player_stats_section(
            match_id="2026080802",
            home_id="FCT",
            away_id="ZEL",
            qa_engine=self.mock_qa,
        )
        mock_sub.assert_called()


if __name__ == "__main__":
    unittest.main()
