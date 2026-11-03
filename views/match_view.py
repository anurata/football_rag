"""
views/match_view.py

3. Match Deep Dive page (Re-architected 5-Section Layout).
Provides a streamlined, modern 5-section watching guide structure:
1. Match Summary (Narrative, Formations, Timeline, Press/Discourse)
2. Player & Coach Ratings (MOM, Ratings with Face Photos)
3. Data Analytics (xG, Shots, 6-Axis Radar, Team Characteristics, Outlook)
4. Tactical Insights & Fact Checks (Anomalies, Hypotheses, Fact Checks)
5. All Player Stats Table (Face Photos, Dynamic Sorting, Deep Link to Player)
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from agent.engine import TacticalAnalystEngine
from agent.gemini_client import GeminiTacticalClient
from agent.objective_profiler import MatchObjectiveProfiler
from agent.player_rater import PlayerRatingGenerator
from agent.qa_engine import TacticalQAEngine
from agent.qualitative_comparator import QualitativeComparator
from views.components.ai_modal import render_ai_button
from views.components.match import (
    render_match_analytics_section,
    render_match_insights_section,
    render_match_player_stats_section,
    render_match_ratings_section,
    render_match_summary_section,
)
from views.navigation import VIEW_MATCH


def _render_top_header(
    selected_match: Dict[str, Any],
    qa_engine: TacticalQAEngine,
    app_helpers: Dict[str, Any],
) -> None:
    """Render top score header, ubiquitous AI button, external links, and context bar."""
    match_id = selected_match.get("match_id", "")
    home_id = selected_match.get("home_team_id", "")
    away_id = selected_match.get("away_team_id", "")

    render_header = app_helpers.get("render_header")
    render_external_links = app_helpers.get("render_external_links_bar")
    render_match_context = app_helpers.get("render_match_context_bar")

    if render_header:
        render_header(selected_match)

    col_ai_bar, _ = st.columns([1, 3])
    with col_ai_bar:
        render_ai_button(
            button_key=f"match_header_ai_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="summary",
            note=f"試合全般 ({home_id} vs {away_id}) の戦況・要約について質問",
            button_label="🤖 この試合についてAIに質問",
        )

    if render_external_links:
        render_external_links(selected_match)
    if render_match_context:
        render_match_context(match_id)


def _render_advanced_tools_expander(
    engine: TacticalAnalystEngine,
    profiler: MatchObjectiveProfiler,
    gemini_client: GeminiTacticalClient,
    match_id: str,
    home_id: str,
    away_id: str,
    summary: Dict[str, Any],
    app_helpers: Dict[str, Any],
) -> None:
    """Render secondary tools (Raw Data, Advanced Tactical Reports, AI Reasoning) in expander."""
    with st.expander("🛠️ 高度戦術レポート ＆ Rawデータ詳細・AI深層推論", expanded=False):
        subtabs = st.tabs(
            [
                "🚀 5大発展戦術レポート",
                "📦 収集Rawデータ詳細",
                "🧠 プロ分析官のAI深層推論",
            ],
        )

        with subtabs[0]:
            render_adv = app_helpers.get("render_advanced_reports_tab")
            if render_adv:
                render_adv(profiler, summary)

        with subtabs[1]:
            render_raw = app_helpers.get("render_raw_data_tab")
            if render_raw:
                render_raw(match_id, summary)

        with subtabs[2]:
            render_reasoning = app_helpers.get("render_ai_reasoning_tab")
            if render_reasoning:
                render_reasoning(engine, gemini_client, match_id, home_id, away_id)


def render_match_view(
    selected_match: Dict[str, Any],
    engine: TacticalAnalystEngine,
    profiler: MatchObjectiveProfiler,
    comparator: QualitativeComparator,
    rater: PlayerRatingGenerator,
    gemini_client: GeminiTacticalClient,
    qa_engine: TacticalQAEngine,
    app_helpers: Dict[str, Any],
) -> None:
    """
    Render Match Deep Dive view, orchestrated into 5 clean core sections
    plus secondary advanced tactical tools.
    """
    match_id = selected_match.get("match_id", "")
    home_id = selected_match.get("home_team_id", "")
    away_id = selected_match.get("away_team_id", "")

    # Top Header & Meta
    _render_top_header(
        selected_match=selected_match,
        qa_engine=qa_engine,
        app_helpers=app_helpers,
    )

    summary = engine.sql_tools.get_match_summary(match_id) or {}
    fetch_reviews = app_helpers.get("fetch_match_reviews")
    reviews = fetch_reviews(match_id) if fetch_reviews else []
    report = profiler.build_15_perspective_report(summary)
    struct_summary = report.get("overall_structure_summary")

    # Section 1: Match Summary
    render_match_summary_section(
        match_id=match_id,
        home_id=home_id,
        away_id=away_id,
        struct_summary=struct_summary,
        qa_engine=qa_engine,
    )

    # Section 2: Player & Coach Ratings
    render_match_ratings_section(
        match_id=match_id,
        home_id=home_id,
        away_id=away_id,
        rater=rater,
        summary=summary,
        qa_engine=qa_engine,
    )

    # Section 3: Match Quantitative Data Analytics
    render_match_analytics_section(
        match_id=match_id,
        home_id=home_id,
        away_id=away_id,
        profiler=profiler,
        summary=summary,
        qa_engine=qa_engine,
    )

    # Section 4: Tactical Insights & Fact Checks
    render_match_insights_section(
        match_id=match_id,
        home_id=home_id,
        away_id=away_id,
        comparator=comparator,
        profiler=profiler,
        summary=summary,
        reviews=reviews,
        qa_engine=qa_engine,
    )

    # Section 5: All Player Stats Table
    render_match_player_stats_section(
        match_id=match_id,
        home_id=home_id,
        away_id=away_id,
        qa_engine=qa_engine,
    )

    # Secondary Advanced Tools
    _render_advanced_tools_expander(
        engine=engine,
        profiler=profiler,
        gemini_client=gemini_client,
        match_id=match_id,
        home_id=home_id,
        away_id=away_id,
        summary=summary,
        app_helpers=app_helpers,
    )
