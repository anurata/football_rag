"""
views/match_view.py

3. Match Deep Dive page (app.py modularization).
Provides full match analytics, multi-perspective reports, player ratings,
and ubiquitous AI dialog integration.
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
from views.navigation import VIEW_MATCH


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
    Render Match Deep Dive view, wrapping existing robust analysis modules
    and adding ubiquitous AI modal buttons to each perspective.
    """
    match_id = selected_match.get("match_id", "")
    home_id = selected_match.get("home_team_id", "")
    away_id = selected_match.get("away_team_id", "")

    # Header components
    render_header = app_helpers.get("render_header")
    render_external_links = app_helpers.get("render_external_links_bar")
    render_match_context = app_helpers.get("render_match_context_bar")
    fetch_reviews = app_helpers.get("fetch_match_reviews")

    if render_header:
        render_header(selected_match)

    # Ubiquitous AI modal header trigger
    col_ai_bar, _ = st.columns([1, 4])
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

    summary = engine.sql_tools.get_match_summary(match_id) or {}
    reviews = fetch_reviews(match_id) if fetch_reviews else []

    tabs = st.tabs(
        [
            "💬 戦術対話QA (Google検索)",
            "📊 客観データ多角分析 (15観点)",
            "⚖️ 定性対比・答え合わせ",
            "🏅 選手・監督採点＆寸評",
            "🚀 5大発展戦術レポート",
            "📈 スタッツグラフ比較",
            "📦 収集Rawデータ詳細",
            "🧠 プロ分析官のAI深層推論",
            "📝 公式レポート・会見全文",
        ],
    )

    # Tab 0: Chat QA Session
    with tabs[0]:
        render_chat = app_helpers.get("render_chat_qa_tab")
        if render_chat:
            render_chat(qa_engine, match_id)

    # Tab 1: Objective Analysis
    with tabs[1]:
        render_ai_button(
            button_key=f"ai_btn_obj_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="objective_analysis",
            note="15観点客観データについて質問",
            button_label="🤖 客観データについてAIに質問",
        )
        render_obj = app_helpers.get("render_objective_perspectives_tab")
        if render_obj:
            render_obj(profiler, summary)

    # Tab 2: Qualitative Comparison
    with tabs[2]:
        render_ai_button(
            button_key=f"ai_btn_comp_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="qualitative_comparison",
            note="定性コメントとデータの整合性について質問",
            button_label="🤖 定性対比についてAIに質問",
        )
        render_comp = app_helpers.get("render_qualitative_comparison_tab")
        if render_comp:
            render_comp(comparator, profiler, match_id, summary, reviews)

    # Tab 3: Player Ratings
    with tabs[3]:
        render_ai_button(
            button_key=f"ai_btn_rate_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="player_ratings",
            note="選手・監督の採点・寸評について質問",
            button_label="🤖 採点・寸評についてAIに質問",
        )
        render_rate = app_helpers.get("render_player_ratings_tab")
        if render_rate:
            render_rate(rater, summary)

    # Tab 4: 5 Advanced Reports
    with tabs[4]:
        render_ai_button(
            button_key=f"ai_btn_adv_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="advanced_reports",
            note="5大発展戦術レポートについて質問",
            button_label="🤖 発展レポートについてAIに質問",
        )
        render_adv = app_helpers.get("render_advanced_reports_tab")
        if render_adv:
            render_adv(profiler, summary)

    # Tab 5: Stats Chart
    with tabs[5]:
        st.subheader("📊 定量スタッツのグラフィカル比較")
        render_chart = app_helpers.get("render_stats_chart")
        if render_chart:
            render_chart(summary, home_id, away_id)

    # Tab 6: Raw Data Explorer
    with tabs[6]:
        render_raw = app_helpers.get("render_raw_data_tab")
        if render_raw:
            render_raw(match_id, summary)

    # Tab 7: AI Reasoning
    with tabs[7]:
        render_reasoning = app_helpers.get("render_ai_reasoning_tab")
        if render_reasoning:
            render_reasoning(engine, gemini_client, match_id, home_id, away_id)

    # Tab 8: Raw Qualitative Reviews
    with tabs[8]:
        st.subheader("📝 公式戦評および監督・選手インタビュー全文")
        if not reviews:
            st.info("定性レポートがまだ登録されていません。")
        else:
            for rev in reviews:
                rtype = rev.get("review_type", "")
                title = rev.get("title") or rtype
                speaker = rev.get("speaker_name") or ""
                with st.expander(
                    f"【{rtype}】{title} {f'({speaker})' if speaker else ''}",
                    expanded=(rtype == "OFFICIAL_REPORT"),
                ):
                    st.markdown(rev.get("content_text", ""))

