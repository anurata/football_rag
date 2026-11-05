"""
views/components/match/report_card_section.py

Match Deep Dive Component: J1 Match Report Card (番記者通信簿).
Displays El Golasso-style 6-dimension report card:
1. S to D Rank & Total Score (out of 60)
2. 6-Axis Radar Chart comparing Home and Away clubs
3. Club-specific evaluation cards with breakdown & reporter critique
"""

from typing import Any, Dict, List, Optional
import plotly.graph_objects as go
import streamlit as st

from agent.objective_profiler import resolve_team_name
from agent.qa_engine import TacticalQAEngine
from pipeline.match_report_card_calculator import MatchReportCardCalculator
from pipeline.team_analytics_engine import get_team_emblem_html
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_MATCH


_RANK_COLORS: Dict[str, str] = {
    "S": "#f59e0b",
    "A+": "#10b981",
    "A-": "#059669",
    "B+": "#3b82f6",
    "B-": "#0284c7",
    "C": "#f97316",
    "D": "#ef4444",
}


@st.cache_data(ttl=600)
def load_match_report_cards(
    match_id: str,
    home_id: str,
    away_id: str,
) -> Dict[str, Any]:
    """Calculate and cache 6-dimension report cards for both clubs."""
    calc = MatchReportCardCalculator()
    home_card = calc.calculate_report_card(match_id=match_id, team_id=home_id)
    away_card = calc.calculate_report_card(match_id=match_id, team_id=away_id)
    return {
        "home": home_card,
        "away": away_card,
    }


def _get_rank_badge_html(rank: str) -> str:
    """Return styled HTML badge for rank."""
    color = _RANK_COLORS.get(rank, "#64748b")
    return (
        f"<span style='background-color: {color}; color: #ffffff; "
        f"padding: 4px 12px; border-radius: 6px; font-weight: 800; "
        f"font-size: 1.1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.25);'>"
        f"{rank} ランク</span>"
    )


def _render_report_card_radar(
    home_card: Dict[str, Any],
    away_card: Dict[str, Any],
    home_name: str,
    away_name: str,
) -> None:
    """Render 6-axis radar chart comparing both clubs (0-10 scale)."""
    categories = [
        "① ゲーム支配",
        "② 個人パワー",
        "③ スタイル発揮",
        "④ 球際",
        "⑤ リレーション",
        "⑥ 興奮度",
    ]

    metric_keys = [
        "game_dominance",
        "individual_power",
        "style_execution",
        "duels_intensity",
        "team_cohesion",
        "excitement_index",
    ]

    h_metrics = home_card.get("metrics", {})
    a_metrics = away_card.get("metrics", {})

    h_scores = [h_metrics.get(k, {}).get("score", 0) for k in metric_keys]
    a_scores = [a_metrics.get(k, {}).get("score", 0) for k in metric_keys]

    fig = go.Figure()

    fig.add_trace(
        go.Scatterpolar(
            r=h_scores + [h_scores[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=f"🔵 {home_name}",
            line=dict(color="#3b82f6", width=2.5),
            fillcolor="rgba(59, 130, 246, 0.25)",
        ),
    )

    fig.add_trace(
        go.Scatterpolar(
            r=a_scores + [a_scores[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=f"🔴 {away_name}",
            line=dict(color="#f43f5e", width=2.5),
            fillcolor="rgba(244, 63, 94, 0.25)",
        ),
    )

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 10],
                tickfont=dict(size=10, color="#94a3b8"),
                gridcolor="#334155",
            ),
            angularaxis=dict(
                tickfont=dict(size=11, color="#f1f5f9", face="bold"),
                gridcolor="#334155",
                linecolor="#475569",
            ),
            bgcolor="rgba(15, 23, 42, 0.6)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        height=380,
        margin=dict(l=40, r=40, t=30, b=30),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.05,
            xanchor="center",
            x=0.5,
            font=dict(color="#cbd5e1", size=12),
        ),
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_metrics_breakdown(metrics: Dict[str, Any]) -> None:
    """Render compact score breakdown bars for 6 dimensions."""
    metric_order = [
        ("game_dominance", "① ゲーム支配"),
        ("individual_power", "② 個人パワー"),
        ("style_execution", "③ スタイル発揮"),
        ("duels_intensity", "④ 球際"),
        ("team_cohesion", "⑤ リレーション"),
        ("excitement_index", "⑥ 興奮度"),
    ]

    for key, label in metric_order:
        m_data = metrics.get(key, {})
        score = m_data.get("score", 0)
        c_label, c_bar, c_val = st.columns([3, 5, 2])
        with c_label:
            st.caption(label)
        with c_bar:
            st.progress(min(1.0, max(0.0, score / 10.0)))
        with c_val:
            st.markdown(f"**{score}** / 10")


def _render_team_card(
    team_card: Dict[str, Any],
    team_id: str,
    team_name: str,
    is_home: bool,
) -> None:
    """Render single club report card with rank, critique, and details."""
    rank = team_card.get("rank", "B+")
    total_score = team_card.get("total_score", 0)
    critique = team_card.get("critique", {})
    metrics = team_card.get("metrics", {})
    reasons = (
        metrics.get("excitement_index", {})
        .get("details", {})
        .get("reasons", [])
    )

    prefix = "🔵 HOME" if is_home else "🔴 AWAY"
    border_color = "#3b82f6" if is_home else "#f43f5e"

    with st.container(border=True):
        # Header Row
        col_emb, col_title, col_rank = st.columns([1, 4, 3])
        with col_emb:
            st.markdown(
                f"<div style='text-align: center; padding-top: 4px;'>"
                f"{get_team_emblem_html(team_id, width=44, height=44)}"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_title:
            st.caption(prefix)
            st.markdown(f"### {team_name}")
        with col_rank:
            st.markdown(
                f"<div style='text-align: right;'>"
                f"{_get_rank_badge_html(rank)}<br>"
                f"<span style='font-size: 1.3rem; font-weight: 700; color: #f8fafc;'>"
                f"{total_score}</span> <span style='font-size: 0.85rem; color: #94a3b8;'>/ 60点</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown(f"**{critique.get('headline', '')}**")
        st.write(critique.get("text", ""))

        st.divider()

        # Breakdown section
        st.markdown("##### 📊 6大評価項目 内訳採点")
        _render_metrics_breakdown(metrics)

        # Drama & Penalty factors
        if reasons:
            with st.expander("⚡ 試合展開・ボーナス／ペナルティ要因", expanded=False):
                for r in reasons:
                    icon = "🟢" if "+" in r else "🔴"
                    st.caption(f"{icon} {r}")


def render_match_report_card_section(
    match_id: str,
    home_id: str,
    away_id: str,
    qa_engine: TacticalQAEngine,
) -> None:
    """
    Render J1 Match Report Card (番記者通信簿) section.
    Includes 6-axis radar chart and club evaluation cards.
    """
    home_name = resolve_team_name(home_id)
    away_name = resolve_team_name(away_id)

    col_title, col_ai = st.columns([3, 1])
    with col_title:
        st.subheader("📰 J1番記者通信簿 (Match Report Card)")
        st.caption(
            "サッカー専門新聞『エル・ゴラッソ』公認基準に基づく6大観点（各10点・計60点満点）による客観採点＆番記者寸評です。"
        )
    with col_ai:
        render_ai_button(
            button_key=f"ai_report_card_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="report_card",
            note=f"試合通信簿 ({home_name} vs {away_name}) の採点理由や勝敗因について質問",
            button_label="🤖 通信簿をAI分析",
        )

    # Load calculated cards
    data = load_match_report_cards(
        match_id=match_id,
        home_id=home_id,
        away_id=away_id,
    )
    home_card = data.get("home", {})
    away_card = data.get("away", {})

    # Top: 6-Axis Radar Chart
    _render_report_card_radar(
        home_card=home_card,
        away_card=away_card,
        home_name=home_name,
        away_name=away_name,
    )

    # Bottom: 2-column comparison cards
    col_home, col_away = st.columns(2)
    with col_home:
        _render_team_card(
            team_card=home_card,
            team_id=home_id,
            team_name=home_name,
            is_home=True,
        )
    with col_away:
        _render_team_card(
            team_card=away_card,
            team_id=away_id,
            team_name=away_name,
            is_home=False,
        )
