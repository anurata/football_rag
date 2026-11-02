"""views package for J-League Watching Guide RAG Dashboard."""

from .navigation import (
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
    render_sidebar_navigation,
)
from .league_view import render_league_view
from .team_view import render_team_view
from .player_view import render_player_view
from .ai_chat_view import render_ai_chat_view
from .match_view import render_match_view
from .settings_view import (
    render_settings_view,
    get_configured_gemini_client,
    init_settings_state,
)

__all__ = [
    "VIEW_LEAGUE",
    "VIEW_TEAM",
    "VIEW_MATCH",
    "VIEW_PLAYER",
    "VIEW_AI_CHAT",
    "VIEW_SETTINGS",
    "VIEW_LABELS",
    "LABEL_TO_VIEW",
    "init_navigation_state",
    "get_current_view",
    "navigate_to",
    "render_sidebar_navigation",
    "render_league_view",
    "render_team_view",
    "render_player_view",
    "render_ai_chat_view",
    "render_match_view",
    "render_settings_view",
    "get_configured_gemini_client",
    "init_settings_state",
]
