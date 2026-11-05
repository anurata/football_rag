"""
views/components/match/__init__.py

Package for Match Deep Dive 5-section components.
"""

from .summary_section import render_match_summary_section
from .report_card_section import render_match_report_card_section
from .ratings_section import render_match_ratings_section
from .analytics_section import render_match_analytics_section
from .insights_section import render_match_insights_section
from .player_stats_section import render_match_player_stats_section

__all__ = [
    "render_match_summary_section",
    "render_match_report_card_section",
    "render_match_ratings_section",
    "render_match_analytics_section",
    "render_match_insights_section",
    "render_match_player_stats_section",
]
