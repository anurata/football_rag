"""
views/navigation.py

Navigation, deep linking, and session state manager for J-League Watching Guide.
Provides SPA-style screen switching across 5 core views and contextual jumping.
"""

from typing import Any, Dict, List, Optional
import streamlit as st

# View Constants
VIEW_LEAGUE = "LEAGUE"
VIEW_TEAM = "TEAM"
VIEW_MATCH = "MATCH"
VIEW_PLAYER = "PLAYER"
VIEW_AI_CHAT = "AI_CHAT"
VIEW_SETTINGS = "SETTINGS"

VIEW_LABELS: Dict[str, str] = {
    VIEW_LEAGUE: "🏆 Jリーグ全体",
    VIEW_TEAM: "🛡️ チーム毎",
    VIEW_MATCH: "⚽ 試合詳細",
    VIEW_PLAYER: "👤 選手名鑑",
    VIEW_AI_CHAT: "🤖 AI対話一覧",
    VIEW_SETTINGS: "⚙️ 設定",
}

LABEL_TO_VIEW: Dict[str, str] = {
    v: k
    for k, v in VIEW_LABELS.items()
}


def init_navigation_state(default_view: str = VIEW_MATCH) -> None:
    """Initialize navigation keys in st.session_state if not present."""
    defaults: Dict[str, Any] = {
        "current_view": default_view,
        "selected_match_id": None,
        "selected_team_id": None,
        "selected_player_id": None,
        "selected_player_name": None,
        "selected_section_key": None,
        "resume_session_id": None,
        "auto_open_ai_modal": False,
        "ai_modal_context": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_current_view() -> str:
    """Return currently active view key."""
    init_navigation_state()
    return st.session_state.get("current_view", VIEW_MATCH)


def navigate_to(
    view: str,
    match_id: Optional[str] = None,
    team_id: Optional[str] = None,
    player_id: Optional[str] = None,
    player_name: Optional[str] = None,
    section_key: Optional[str] = None,
    resume_session_id: Optional[str] = None,
    auto_open_ai: bool = False,
    trigger_rerun: bool = True,
) -> None:
    """
    Seamless deep-linking transition to a target view and target context.
    Optionally restores an AI chat session and requests auto-opening modal.
    """
    init_navigation_state()
    st.session_state["current_view"] = view

    if match_id is not None:
        st.session_state["selected_match_id"] = match_id
    if team_id is not None:
        st.session_state["selected_team_id"] = team_id
    if player_id is not None:
        st.session_state["selected_player_id"] = player_id
    if player_name is not None:
        st.session_state["selected_player_name"] = player_name
    if section_key is not None:
        st.session_state["selected_section_key"] = section_key

    st.session_state["resume_session_id"] = resume_session_id
    st.session_state["auto_open_ai_modal"] = auto_open_ai

    if trigger_rerun:
        _safe_rerun()


def _safe_rerun() -> None:
    """Call st.rerun safely, catching environment exceptions in non-Streamlit tests."""
    try:
        if hasattr(st, "rerun"):
            st.rerun()
    except Exception:
        # Gracefully handle when running in headless unit tests without active Streamlit script context
        pass


def render_sidebar_navigation() -> str:
    """
    Render top-level sidebar navigation widget (segmented radio buttons).
    Returns the selected view key.
    """
    init_navigation_state()
    current_view = st.session_state.get("current_view", VIEW_MATCH)

    options = list(VIEW_LABELS.values())
    current_label = VIEW_LABELS.get(current_view, VIEW_LABELS[VIEW_MATCH])
    current_index = options.index(current_label) if current_label in options else 0

    st.sidebar.markdown("### 🧭 観戦ガイド・ナビゲーション")
    selected_label = st.sidebar.radio(
        label="画面切り替え",
        options=options,
        index=current_index,
        label_visibility="collapsed",
        key="sidebar_view_radio",
    )

    new_view = LABEL_TO_VIEW.get(selected_label, VIEW_MATCH)
    if new_view != current_view:
        st.session_state["current_view"] = new_view
        _safe_rerun()

    return new_view

