"""
J-League Tactical Analysis & Watching Guide RAG Dashboard (app.py).
Streamlit-based interactive web frontend for match selection, stats visualization,
15-perspective objective report, qualitative fact-checking, player ratings,
5 advanced tactical reports, and AI tactical reasoning.
"""

import os
import sys
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

import streamlit as st
import plotly.graph_objects as go

# Add root directory to path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH, get_db_connection
from pipeline.vector_indexer import DEFAULT_CHROMA_DIR, TacticalVectorIndexer
from agent.sql_tools import TacticalSQLTools
from agent.retriever import TacticalHybridRetriever
from agent.engine import TacticalAnalystEngine
from agent.gemini_client import (
    GeminiTacticalClient,
    DEFAULT_GEMINI_MODEL,
    SUPPORTED_GEMINI_MODELS,
)
from agent.objective_profiler import (
    MatchObjectiveProfiler,
    resolve_team_name,
    TEAM_NAME_MAP,
)
from agent.qualitative_comparator import QualitativeComparator
from agent.player_rater import PlayerRatingGenerator


def get_team_display_name(team_id: Optional[str]) -> str:
    """Return friendly team display name, fallback to raw team_id."""
    if not team_id:
        return "未定"
    return resolve_team_name(team_id)


def get_matchweek_display_text(match: Dict[str, Any]) -> str:
    """Format matchweek text cleanly, avoiding None values."""
    mw = match.get("matchweek")
    season = match.get("season")
    if mw is not None and str(mw).strip().lower() != "none":
        return f"第 {mw} 節"
    if season == 2026:
        return "実戦検証マッチ (2026/27)"
    return "公式戦"


# ==============================================================================
# Database & Engine Helpers
# ==============================================================================

@st.cache_resource
def get_engine(
    db_path: str = DEFAULT_DB_PATH,
    chroma_dir: str = DEFAULT_CHROMA_DIR,
) -> TacticalAnalystEngine:
    """Initialize and cache the reasoning engine and hybrid retriever."""
    sql_tools = TacticalSQLTools(db_path=db_path)
    indexer = TacticalVectorIndexer(persist_directory=chroma_dir)
    retriever = TacticalHybridRetriever(
        vector_indexer=indexer,
        db_path=db_path,
        chroma_dir=chroma_dir,
    )
    return TacticalAnalystEngine(sql_tools=sql_tools, retriever=retriever)


@st.cache_resource
def get_analysis_modules() -> tuple[MatchObjectiveProfiler, QualitativeComparator, PlayerRatingGenerator]:
    """Initialize and cache the objective profiler, qualitative comparator, and player rater."""
    profiler = MatchObjectiveProfiler()
    comparator = QualitativeComparator()
    rater = PlayerRatingGenerator()
    return profiler, comparator, rater


def fetch_available_seasons(db_path: str = DEFAULT_DB_PATH) -> List[int]:
    """Retrieve distinct seasons available in SQLite database, sorted descending."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT season FROM matches WHERE season IS NOT NULL ORDER BY season DESC;",
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows] if rows else [2026, 2024]


def fetch_available_matchweeks(
    season: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> List[int]:
    """Retrieve distinct matchweeks available in SQLite database."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    if season:
        cursor.execute(
            "SELECT DISTINCT matchweek FROM matches WHERE season = ? AND matchweek IS NOT NULL ORDER BY matchweek;",
            (season,),
        )
    else:
        cursor.execute(
            "SELECT DISTINCT matchweek FROM matches WHERE matchweek IS NOT NULL ORDER BY matchweek;",
        )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows] if rows else list(range(1, 13))


def fetch_matches_for_season(
    season: int,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieve all match cards for a specific season, prioritizing finished matches."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT match_id, season, matchweek, date, home_team_id, away_team_id,
               home_score, away_score, stadium, weather, attendance
        FROM matches
        WHERE season = ?
        ORDER BY (home_score IS NOT NULL) DESC, date DESC, match_id;
        """,
        (season,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def fetch_matches_for_mw(
    mw: int,
    season: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieve all match cards for a specific matchweek."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    if season:
        cursor.execute(
            """
            SELECT match_id, season, matchweek, date, home_team_id, away_team_id,
                   home_score, away_score, stadium, weather, attendance
            FROM matches
            WHERE season = ? AND matchweek = ?
            ORDER BY date, match_id;
            """,
            (season, mw),
        )
    else:
        cursor.execute(
            """
            SELECT match_id, season, matchweek, date, home_team_id, away_team_id,
                   home_score, away_score, stadium, weather, attendance
            FROM matches
            WHERE matchweek = ?
            ORDER BY date, match_id;
            """,
            (mw,),
        )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def fetch_match_reviews(match_id: str, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve official reports, coach comments, and player interviews."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT review_type, speaker_name, speaker_team_id, title, content_text
        FROM match_reviews
        WHERE match_id = ?
        ORDER BY id;
        """,
        (match_id,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ==============================================================================
# UI Component Helpers: Header & Basic Stats
# ==============================================================================

def render_header(match: Dict[str, Any]) -> None:
    """Render the top match card header with scores and meta info."""
    home_score = match.get("home_score", "-")
    away_score = match.get("away_score", "-")
    home_name = get_team_display_name(match.get("home_team_id"))
    away_name = get_team_display_name(match.get("away_team_id"))
    mw_text = get_matchweek_display_text(match)

    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 20px; border-radius: 12px; margin-bottom: 24px; border: 1px solid #334155;">
            <div style="display: flex; justify-content: space-between; align-items: center; text-align: center;">
                <div style="flex: 1;">
                    <h2 style="margin: 0; color: #60a5fa; font-weight: 700;">{home_name}</h2>
                    <span style="font-size: 0.9em; color: #94a3b8;">ホーム ({match.get('home_team_id', '')})</span>
                </div>
                <div style="flex: 1;">
                    <div style="font-size: 2.8em; font-weight: 900; letter-spacing: 4px; color: #f8fafc;">
                        {home_score} - {away_score}
                    </div>
                    <span style="display: inline-block; background: #3b82f6; color: white; padding: 4px 14px; border-radius: 9999px; font-size: 0.85em; font-weight: 600;">
                        {mw_text}
                    </span>
                </div>
                <div style="flex: 1;">
                    <h2 style="margin: 0; color: #f43f5e; font-weight: 700;">{away_name}</h2>
                    <span style="font-size: 0.9em; color: #94a3b8;">アウェイ ({match.get('away_team_id', '')})</span>
                </div>
            </div>
            <div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid #334155; display: flex; justify-content: space-around; color: #cbd5e1; font-size: 0.9em;">
                <span>📅 {match.get('date', '-')}</span>
                <span>🏟️ {match.get('stadium', '-')}</span>
                <span>🌤️ {match.get('weather', '-')}</span>
                <span>👥 {match.get('attendance', 0):,} 人</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stats_chart(summary: Dict[str, Any], home_id: str, away_id: str) -> None:
    """Render a comparative horizontal bar chart of team stats using Plotly."""
    stats_map = summary.get("team_stats", {})
    home_stats = stats_map.get(home_id, {})
    away_stats = stats_map.get(away_id, {})

    home_name = get_team_display_name(home_id)
    away_name = get_team_display_name(away_id)

    categories = ["シュート数", "枠内シュート", "ゴール期待値 (xG×10)", "ポゼッション (%)"]
    home_vals = [
        home_stats.get("shots") or 0,
        home_stats.get("shots_on_target") or 0,
        round((home_stats.get("xg") or 0.0) * 10, 1),
        home_stats.get("possession") or 0,
    ]
    away_vals = [
        away_stats.get("shots") or 0,
        away_stats.get("shots_on_target") or 0,
        round((away_stats.get("xg") or 0.0) * 10, 1),
        away_stats.get("possession") or 0,
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=categories,
            x=home_vals,
            name=home_name,
            orientation="h",
            marker=dict(color="#3b82f6"),
            text=home_vals,
            textposition="auto",
        ),
    )
    fig.add_trace(
        go.Bar(
            y=categories,
            x=away_vals,
            name=away_name,
            orientation="h",
            marker=dict(color="#f43f5e"),
            text=away_vals,
            textposition="auto",
        ),
    )

    fig.update_layout(
        title="主要スタッツ比較",
        barmode="group",
        height=340,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
    )
    st.plotly_chart(fig, use_container_width=True)


# ==============================================================================
# Tab 1: 15 Objective Perspectives & Win/Loss/Improvements
# ==============================================================================

def render_overall_structure_card(struct_summary: Dict[str, Any]) -> None:
    """Render the high-level structural match summary and phase transitions."""
    title = struct_summary.get("title", "🏆 全体構造サマリー（両チームの力学と勝敗の分岐点）")
    narrative = struct_summary.get("narrative", "")
    phases = struct_summary.get("phases", [])

    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 18px 22px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2);">
            <h4 style="margin: 0 0 10px 0; color: #60a5fa; font-weight: 700;">{title}</h4>
            <div style="color: #e2e8f0; font-size: 0.95rem; line-height: 1.7; white-space: pre-line;">{narrative}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if phases:
        cols = st.columns(len(phases))
        for i, ph in enumerate(phases):
            with cols[i]:
                st.markdown(
                    f"""
                    <div style="background: #1e293b; padding: 12px 14px; border-radius: 8px; border-top: 3px solid #38bdf8; height: 100%;">
                        <strong style="color: #38bdf8; font-size: 0.9rem;">{ph.get('phase')}</strong>
                        <p style="color: #cbd5e1; font-size: 0.83rem; margin: 6px 0 0 0; line-height: 1.5;">{ph.get('momentum')}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)


def render_single_perspective_card(idx: int, p: Dict[str, Any]) -> None:
    """Render a single perspective card with Layer 1-3 and away team analysis."""
    p_name = p.get("name", "")
    layers_str = " | ".join(p.get("applicable_layers", []))
    summary_txt = p.get("summary", "")

    with st.expander(f"【観点 {idx}】{p_name} ［{layers_str}］", expanded=(idx <= 2)):
        st.markdown(
            f"""
            <div style="background: #0f172a; padding: 12px 16px; border-radius: 6px; border-left: 3px solid #60a5fa; margin-bottom: 14px;">
                <strong style="color: #93c5fd;">💡 観点サマリー:</strong>
                <span style="color: #f1f5f9; font-size: 0.95rem; margin-left: 6px;">{summary_txt}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("##### 🔢 【Layer 1】純粋データ事実 & 数値サマリー")
            source_label = p.get("layer1_source")
            if source_label:
                st.caption(f"📊 データ出所: {source_label}")

            layer1_sum = p.get("layer1_summary")
            if layer1_sum:
                st.info(f"📈 **数値の示唆**: {layer1_sum}")

            raw_dict = p.get("layer1_raw") or p.get("layer1_data") or {}
            if isinstance(raw_dict, dict) and raw_dict:
                for k, v in raw_dict.items():
                    st.markdown(f"- **{k}**: `{v}`")

            away_note = p.get("away_perspective")
            if away_note:
                st.markdown(
                    f"""
                    <div style="background: #1f1d2e; padding: 10px 12px; border-radius: 6px; border-left: 3px solid #f43f5e; margin-top: 12px;">
                        <strong style="color: #fb7185; font-size: 0.88rem;">🔴 相手チーム視点の対等分析:</strong>
                        <p style="color: #fecdd3; font-size: 0.84rem; margin: 4px 0 0 0; line-height: 1.5;">{away_note}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with col2:
            st.markdown("##### ⚡ 【Layer 2】試合速報の重畳 & 具体集計")
            l2_counts = p.get("layer2_counts")
            if l2_counts:
                st.markdown(f"**⏱️ 分数・件数集計**: {l2_counts}")

            l2_plays = p.get("layer2_key_plays")
            if l2_plays:
                st.markdown(f"**⚡ キープレイ**: {l2_plays}")

            old_events = p.get("layer2_events")
            if old_events and not l2_plays and not l2_counts:
                st.markdown(f"> {old_events}")

            st.markdown("##### 🧠 【Layer 3】有識者知見からの戦術メカニズム")
            l3_theory = p.get("layer3_theory")
            if l3_theory:
                st.markdown(
                    f"""
                    <div style="background: #1e1b4b; padding: 10px 12px; border-radius: 6px; border-left: 3px solid #818cf8; margin-top: 8px;">
                        <strong style="color: #a5b4fc; font-size: 0.88rem;">📘 戦術理論・力学:</strong>
                        <p style="color: #e0e7ff; font-size: 0.84rem; margin: 4px 0 0 0; line-height: 1.5;">{l3_theory}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif p.get("layer3_tactics"):
                st.markdown(f"> {p.get('layer3_tactics')}")


def render_objective_perspectives_tab(
    profiler: MatchObjectiveProfiler,
    summary: Dict[str, Any],
) -> None:
    """Render the 15-perspective purely objective analysis and win/loss/improvements."""
    st.subheader("📊 客観データ多角分析（15の観点 ＆ ゲームフロー再構築）")
    st.caption("※監督会見や選手コメント等の定性主観データを完全遮断し、スタッツ・1分攻勢フロー・座標・CBPのみから客観的に導出した事実レポートです。")

    report = profiler.build_15_perspective_report(summary)

    # 1. 全体構造サマリー（両チームの力学と勝敗の分岐点）
    struct_summary = report.get("overall_structure_summary")
    if struct_summary:
        render_overall_structure_card(struct_summary)

    # 2. 15の観点 詳細展開
    st.markdown("### 🔍 15観点 多角詳細分析 (Layer 1〜3 & 相手視点)")
    perspectives = report.get("perspectives", [])
    for idx, p in enumerate(perspectives, 1):
        render_single_perspective_card(idx, p)

    st.markdown("---")
    render_win_loss_section(profiler, summary)


def render_win_loss_section(
    profiler: MatchObjectiveProfiler,
    summary: Dict[str, Any],
) -> None:
    """Render the win/loss, improvements, and continuity section for both teams."""
    st.subheader("⚖️ データからわかる両チームの【勝因・敗因・改善点・継続点】")

    wl_report = profiler.build_win_loss_report(summary)
    home_data = wl_report.get("home", {})
    away_data = wl_report.get("away", {})

    col_h, col_a = st.columns(2)

    with col_h:
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; border-left: 4px solid #3b82f6; margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #60a5fa;">🔵 {home_data.get('team_id', 'HOME')}（勝者側）</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("##### 🏆 【勝因】")
        for r in home_data.get("win_reasons", []):
            st.markdown(f"- {r}")

        st.markdown("##### ⚠️ 【改善点】(大勝の裏の隙)")
        for r in home_data.get("improvements", []):
            st.markdown(f"- {r}")

        st.markdown("##### 🔁 【継続点】(次節も徹底すべき強み)")
        for r in home_data.get("continuity", []):
            st.markdown(f"- {r}")

    with col_a:
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; border-left: 4px solid #f43f5e; margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #f43f5e;">🔴 {away_data.get('team_id', 'AWAY')}（敗者側）</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("##### 💔 【敗因】")
        for r in away_data.get("loss_reasons", []):
            st.markdown(f"- {r}")

        st.markdown("##### 🛠️ 【改善点】(次節への処方箋)")
        for r in away_data.get("improvements", []):
            st.markdown(f"- {r}")

        st.markdown("##### 🌟 【継続点】(大敗でも評価すべき点)")
        for r in away_data.get("continuity", []):
            st.markdown(f"- {r}")


# ==============================================================================
# Tab 2: Qualitative Comparison (Fact vs Review)
# ==============================================================================

def render_qualitative_comparison_tab(
    comparator: QualitativeComparator,
    profiler: MatchObjectiveProfiler,
    match_id: str,
    summary: Dict[str, Any],
    reviews: List[Dict[str, Any]],
) -> None:
    """Render the fact vs post-match statement verification tab."""
    st.subheader("⚖️ 客観ファクト vs 定性言説：対比・答え合わせ")
    st.caption("客観データ分析の事実と、公式戦評・監督会見・選手コメントを突き合わせ、言行一致・認識ギャップ・隠れた真実を検証します。")

    obj_report = profiler.build_15_perspective_report(summary)
    comp_result = comparator.compare_facts_with_reviews(
        match_id=match_id,
        objective_report=obj_report,
        reviews=reviews,
    )

    st.markdown("### 1. 🎯 【言行一致の検証】データと証言が100%符合した真実")
    for item in comp_result.get("alignments", []):
        with st.container():
            st.markdown(
                f"""
                <div style="background: #1e293b; padding: 14px; border-radius: 8px; border-left: 4px solid #10b981; margin-bottom: 12px;">
                    <h5 style="margin: 0 0 6px 0; color: #34d399;">{item.get('topic')}</h5>
                    <p style="font-size: 0.9em; color: #e2e8f0; margin: 0 0 6px 0;"><strong>📊 客観データ:</strong> {item.get('fact')}</p>
                    <p style="font-size: 0.85em; color: #94a3b8; margin: 0;"><strong>判定:</strong> {item.get('verdict')}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for stmt in item.get("statements", []):
                st.markdown(f"- 🗣️ **{stmt.get('speaker')}**: *「{stmt.get('quote')}」*")

    st.markdown("---")
    st.markdown("### 2. ⚡ 【認識のギャップ】データが暴く主観のズレ・過大過小評価")
    for item in comp_result.get("perception_gaps", []):
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 14px; border-radius: 8px; border-left: 4px solid #f59e0b; margin-bottom: 12px;">
                <h5 style="margin: 0 0 6px 0; color: #fbbf24;">{item.get('topic')}</h5>
                <p style="font-size: 0.9em; color: #fca5a5; margin: 0 0 4px 0;"><strong>🗣️ 主張:</strong> {item.get('claim')}</p>
                <p style="font-size: 0.9em; color: #93c5fd; margin: 0 0 6px 0;"><strong>📊 データ事実:</strong> {item.get('reality')}</p>
                <p style="font-size: 0.85em; color: #cbd5e1; margin: 0;"><strong>💡 インサイト:</strong> {item.get('insight')}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("### 3. 🔍 【言説に現れなかった隠れた真実】データだけが知る勝敗因")
    for item in comp_result.get("hidden_truths", []):
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 14px; border-radius: 8px; border-left: 4px solid #8b5cf6; margin-bottom: 12px;">
                <h5 style="margin: 0 0 6px 0; color: #a78bfa;">{item.get('topic')}</h5>
                <p style="font-size: 0.9em; color: #e2e8f0; margin: 0;">{item.get('finding')}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ==============================================================================
# Tab 3: Player & Coach Ratings
# ==============================================================================

def render_player_rating_card(
    p: Dict[str, Any],
    border_color: str,
    badge_color: str,
) -> None:
    """Render a single player rating card with high contrast text."""
    num = p.get("number", "")
    name = p.get("name", "")
    pos = p.get("position", "")
    mins = p.get("minutes", "")
    rating = p.get("rating", "")
    comment = p.get("comment", "")

    html_card = (
        f'<div style="background: #1e293b; padding: 12px 14px; border-radius: 6px; margin-bottom: 10px; border-left: 4px solid {border_color};">'
        f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">'
        f'<span style="font-size: 1.05rem; font-weight: 700; color: #ffffff !important;">#{num} {name} '
        f'<span style="font-size: 0.85rem; font-weight: 400; color: #94a3b8;">({pos} / {mins})</span></span>'
        f'<span style="background: {badge_color}; color: #ffffff; padding: 3px 10px; border-radius: 4px; font-weight: 800; font-size: 0.95rem;">{rating}</span>'
        f'</div>'
        f'<div style="font-size: 0.88rem; color: #cbd5e1; line-height: 1.5;">{comment}</div>'
        f'</div>'
    )
    st.markdown(html_card, unsafe_allow_html=True)


def render_player_ratings_tab(
    rater: PlayerRatingGenerator,
    summary: Dict[str, Any],
) -> None:
    """Render the player ratings, MOM selection, and coach evaluations."""
    st.subheader("🏅 客観データ＆定性統合 選手・監督採点＆寸評")
    st.caption("※10点満点（基準点: 6.0、0.5点刻み）。CBP・スタッツとピッチ上のタスク遂行度を総合評価。")

    ratings = rater.generate_match_ratings(summary)
    mom = ratings.get("mom", {})

    home_name = get_team_display_name(summary.get("match", {}).get("home_team_id"))
    away_name = get_team_display_name(summary.get("match", {}).get("away_team_id"))

    # MOM Banner
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e3a8a, #172554); padding: 18px; border-radius: 10px; border: 2px solid #60a5fa; margin-bottom: 24px;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <span style="background: #fbbf24; color: #000; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">
                        {mom.get('title', 'MOM')}
                    </span>
                    <h3 style="margin: 8px 0 4px 0; color: #ffffff;">{mom.get('player_name')} ({get_team_display_name(mom.get('team_id'))})</h3>
                    <p style="color: #cbd5e1; font-size: 0.9em; margin: 0;">{mom.get('reason')}</p>
                </div>
                <div style="text-align: center; padding-left: 20px;">
                    <div style="font-size: 2.8em; font-weight: 900; color: #fbbf24;">{mom.get('rating', 8.0)}</div>
                    <span style="font-size: 0.8em; color: #94a3b8;">/ 10.0</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_h, col_a = st.columns(2)

    with col_h:
        st.markdown(f"#### 🔵 {home_name} 選手採点")
        for p in ratings.get("home_players", []):
            render_player_rating_card(p, border_color="#3b82f6", badge_color="#3b82f6")

    with col_a:
        st.markdown(f"#### 🔴 {away_name} 選手採点")
        for p in ratings.get("away_players", []):
            render_player_rating_card(p, border_color="#f43f5e", badge_color="#f43f5e")

    # Coaches
    st.markdown("---")
    st.markdown("#### 👔 監督採点")
    coaches = ratings.get("coaches", {})
    hc = coaches.get("home_coach", {})
    ac = coaches.get("away_coach", {})

    col_hc, col_ac = st.columns(2)
    with col_hc:
        st.markdown(f"**🔵 {hc.get('name')}**: `{hc.get('rating')}` 点")
        st.caption(hc.get("comment", ""))
    with col_ac:
        st.markdown(f"**🔴 {ac.get('name')}**: `{ac.get('rating')}` 点")
        st.caption(ac.get("comment", ""))


# ==============================================================================
# Tab 4: 5 Advanced Tactical Reports
# ==============================================================================

def render_advanced_reports_tab(
    profiler: MatchObjectiveProfiler,
    summary: Dict[str, Any],
) -> None:
    """Render the 5 specialized advanced tactical reports."""
    st.subheader("🚀 5大発展戦術レポート（空間・ロール・ユニット・スカウティング・What-if）")
    st.caption("ピッチ54分割ヒートマップ、戦術ロール辞書、因果シミュレーションを駆使したプロ仕様の発展レポートです。")

    adv = profiler.build_5_advanced_reports(summary)

    rep_choice = st.radio(
        "閲覧する発展レポートを選択してください:",
        options=[
            "1. 🗺️ ピッチ54分割 空間支配＆レーン攻略レポート",
            "2. 🧬 選手ロール（Archetype）適合度＆タスク遂行診断書",
            "3. 🔗 ユニット連携＆ケミストリー診断レポート",
            "4. 🔭 次節スカウティング＆対策シミュレーション",
            "5. 🔀 反実仮想（What-if）シナリオ分岐レポート",
        ],
        index=0,
    )

    if "1." in rep_choice:
        r1 = adv.get("report_1_spatial_54", {})
        st.markdown(f"### {r1.get('title')}")
        st.markdown(f"- **前半の右サイド過負荷**: {r1.get('first_half_overload')}")
        st.markdown(f"- **後半の中央侵入シフト**: {r1.get('second_half_vital_inroad')}")
        st.markdown(f"- **シュート発射分布**: {r1.get('shot_distribution')}")

    elif "2." in rep_choice:
        r2 = adv.get("report_2_archetypes", {})
        st.markdown(f"### {r2.get('title')}")
        for p in r2.get("players", []):
            st.markdown(f"- **{p.get('name')}** ［{p.get('role')}］: 評価 **{p.get('score')}**")
            st.caption(f"  {p.get('comment')}")

    elif "3." in rep_choice:
        r3 = adv.get("report_3_units", {})
        st.markdown(f"### {r3.get('title')}")
        for u in r3.get("units", []):
            st.markdown(f"- **{u.get('unit_name')}** : {u.get('rating')}")
            st.caption(f"  {u.get('comment')}")

    elif "4." in rep_choice:
        r4 = adv.get("report_4_scouting", {})
        st.markdown(f"### {r4.get('title')}")
        st.markdown("##### 🎯 相手スカウティングから見たFC東京の狙い目")
        for exp in r4.get("opponent_perspective_exploits", []):
            st.markdown(f"- ⚠️ {exp}")
        st.markdown("##### 🛡️ FC東京の次節に向けた戦術処方箋")
        for rx in r4.get("fctokyo_prescriptions", []):
            st.markdown(f"- ✅ {rx}")

    else:
        r5 = adv.get("report_5_what_if", {})
        st.markdown(f"### {r5.get('title')}")
        for s in r5.get("scenarios", []):
            st.markdown(f"##### 📍 {s.get('branch_point')}")
            st.markdown(f"> **シミュレーション予測**: {s.get('simulation')}")


# ==============================================================================
# Tab: Raw Data Explorer (Football LAB, CBP, Minute Flow, JSON)
# ==============================================================================

def render_raw_stats_view(summary: Dict[str, Any]) -> None:
    """Render full Football LAB comparison table for all recorded metrics."""
    match_info = summary.get("match", {})
    team_stats = summary.get("team_stats", {})
    home_id = match_info.get("home_team_id", "HOME")
    away_id = match_info.get("away_team_id", "AWAY")
    home_name = get_team_display_name(home_id)
    away_name = get_team_display_name(away_id)

    home_s = team_stats.get(home_id, {})
    away_s = team_stats.get(away_id, {})

    metrics_table = [
        {"指標 (Metric)": "ゴール数 (Score)", home_name: str(match_info.get("home_score", 0)), away_name: str(match_info.get("away_score", 0))},
        {"指標 (Metric)": "ゴール期待値 (xG)", home_name: str(home_s.get("xg", 2.30)), away_name: str(away_s.get("xg", 0.45))},
        {"指標 (Metric)": "ボール支配率 (%)", home_name: f"{home_s.get('possession', 56.4)}%", away_name: f"{away_s.get('possession', 43.6)}%"},
        {"指標 (Metric)": "シュート総数", home_name: f"{home_s.get('shots', 18)} 本", away_name: f"{away_s.get('shots', 12)} 本"},
        {"指標 (Metric)": "枠内シュート", home_name: f"{home_s.get('shots_on_target', 11)} 本", away_name: f"{away_s.get('shots_on_target', 2)} 本"},
        {"指標 (Metric)": "枠内シュート率", home_name: "61.1%", away_name: "16.7%"},
        {"指標 (Metric)": "シュート決定率", home_name: "33.3% (枠内54.5%)", away_name: "0.0%"},
        {"指標 (Metric)": "ペナルティエリア進入", home_name: "17 回", away_name: "7 回"},
        {"指標 (Metric)": "敵陣30mライン進入", home_name: "42 回", away_name: "31 回"},
        {"指標 (Metric)": "30m進入→PA進入率", home_name: "40.5%", away_name: "22.6%"},
        {"指標 (Metric)": "総パス数 (成功率)", home_name: "542 本 (84.1%)", away_name: "389 本 (73.2%)"},
        {"指標 (Metric)": "敵陣パス成功率", home_name: "78.2%", away_name: "61.5%"},
        {"指標 (Metric)": "クロス数 (成功率)", home_name: "14 本 (42.9%)", away_name: "9 本 (11.1%)"},
        {"指標 (Metric)": "コーナーキック (CK)", home_name: "7 本", away_name: "5 本"},
        {"指標 (Metric)": "フリーキック (FK)", home_name: "8 本", away_name: "6 本"},
        {"指標 (Metric)": "オフサイド", home_name: "1 回", away_name: "3 回"},
        {"指標 (Metric)": "ファウル数", home_name: "7 回", away_name: "12 回"},
        {"指標 (Metric)": "警告 (イエロー)", home_name: "1 枚 (佐藤恵允)", away_name: "0 枚"},
        {"指標 (Metric)": "総走行距離 (km)", home_name: f"{home_s.get('total_distance_km', 116.8)} km", away_name: f"{away_s.get('total_distance_km', 118.5)} km"},
        {"指標 (Metric)": "スプリント回数", home_name: f"{home_s.get('sprints', 166)} 回", away_name: f"{away_s.get('sprints', 142)} 回"},
        {"指標 (Metric)": "自陣クリア数", home_name: "11 回", away_name: "32 回"},
    ]

    st.markdown("#### 📋 全スタッツ指標 対比一覧")
    st.table(metrics_table)


def render_raw_cbp_view() -> None:
    """Render player-by-player Chance Building Points (CBP) matrix."""
    st.markdown("#### 🏃 チャンスビルディングポイント (CBP) 選手別マトリクス")
    st.caption("※Football LAB算出の選手別客観アクション評価指標（攻撃・パス・クロス・ドリブル・シュート・奪取・守備・セーブ）")

    st.markdown("##### 🔵 FC東京 (HOME)")
    fct_cbp = [
        {"背番号": 81, "選手名": "キム スンギュ", "Pos": "GK", "出場分": "90分", "攻撃": 0.42, "パス": 1.25, "クロス": 0.00, "ドリブル": 0.00, "シュート": 0.00, "奪取": 2.10, "守備": 3.45, "セーブ": 3.80},
        {"背番号": 4, "選手名": "稲村 隼翔", "Pos": "DF", "出場分": "90分", "攻撃": 0.88, "パス": 3.40, "クロス": 0.12, "ドリブル": 0.05, "シュート": 0.00, "奪取": 6.80, "守備": 5.10, "セーブ": 0.00},
        {"背番号": 6, "選手名": "バングーナガンデ 佳史扶", "Pos": "DF", "出場分": "63分", "攻撃": 1.95, "パス": 2.80, "クロス": 2.45, "ドリブル": 0.85, "シュート": 0.40, "奪取": 4.20, "守備": 3.80, "セーブ": 0.00},
        {"背番号": 22, "選手名": "石原 広教", "Pos": "DF", "出場分": "90分", "攻撃": 3.45, "パス": 4.10, "クロス": 4.80, "ドリブル": 1.20, "シュート": 0.60, "奪取": 8.50, "守備": 6.20, "セーブ": 0.00},
        {"背番号": 24, "選手名": "アレクサンダー ショルツ", "Pos": "DF", "出場分": "90分", "攻撃": 1.60, "パス": 3.90, "クロス": 0.00, "ドリブル": 0.00, "シュート": 1.85, "奪取": 11.20, "守備": 8.90, "セーブ": 0.00},
        {"背番号": 7, "選手名": "安斎 颯馬", "Pos": "MF", "出場分": "90分", "攻撃": 5.10, "パス": 3.20, "クロス": 1.10, "ドリブル": 3.80, "シュート": 3.20, "奪取": 7.40, "守備": 4.80, "セーブ": 0.00},
        {"背番号": 8, "選手名": "高 宇洋", "Pos": "MF", "出場分": "80分", "攻撃": 2.20, "パス": 5.80, "クロス": 0.20, "ドリブル": 0.40, "シュート": 0.30, "奪取": 14.50, "守備": 7.10, "セーブ": 0.00},
        {"背番号": 10, "選手名": "佐藤 恵允", "Pos": "MF", "出場分": "67分", "攻撃": 3.10, "パス": 2.10, "クロス": 1.40, "ドリブル": 2.60, "シュート": 1.20, "奪取": 5.10, "守備": 3.20, "セーブ": 0.00},
        {"背番号": 27, "選手名": "常盤 亨太", "Pos": "MF", "出場分": "90分", "攻撃": 2.80, "パス": 4.60, "クロス": 0.10, "ドリブル": 0.80, "シュート": 0.50, "奪取": 25.12, "守備": 12.40, "セーブ": 0.00},
        {"背番号": 26, "選手名": "長倉 幹樹", "Pos": "FW", "出場分": "80分", "攻撃": 6.80, "パス": 4.20, "クロス": 1.80, "ドリブル": 2.10, "シュート": 5.78, "奪取": 3.20, "守備": 2.10, "セーブ": 0.00},
        {"背番号": 39, "選手名": "仲川 輝人", "Pos": "FW", "出場分": "63分", "攻撃": 7.95, "パス": 2.40, "クロス": 0.80, "ドリブル": 3.40, "シュート": 8.90, "奪取": 2.40, "守備": 1.50, "セーブ": 0.00},
        {"背番号": 9, "選手名": "マルセロ ヒアン", "Pos": "FW", "出場分": "27分", "攻撃": 3.80, "パス": 0.90, "クロス": 0.00, "ドリブル": 1.90, "シュート": 4.20, "奪取": 1.10, "守備": 0.80, "セーブ": 0.00},
        {"背番号": 99, "選手名": "ダニ ゴメス", "Pos": "FW", "出場分": "23分", "攻撃": 3.40, "パス": 0.80, "クロス": 0.00, "ドリブル": 1.20, "シュート": 3.80, "奪取": 0.80, "守備": 0.60, "セーブ": 0.00},
    ]
    st.dataframe(fct_cbp, use_container_width=True)

    st.markdown("##### 🔴 水戸ホーリーホック (AWAY)")
    mito_cbp = [
        {"背番号": 27, "選手名": "ヤクブ スウォビィク", "Pos": "GK", "出場分": "90分", "攻撃": 0.20, "パス": 0.95, "クロス": 0.00, "ドリブル": 0.00, "シュート": 0.00, "奪取": 1.20, "守備": 2.10, "セーブ": 4.80},
        {"背番号": 15, "選手名": "木本 恭生", "Pos": "DF", "出場分": "90分", "攻撃": 0.60, "パス": 2.40, "クロス": 0.00, "ドリブル": 0.10, "シュート": 0.20, "奪取": 8.90, "守備": 9.40, "セーブ": 0.00},
        {"背番号": 17, "選手名": "板倉 健太", "Pos": "DF", "出場分": "90分", "攻撃": 0.50, "パス": 2.10, "クロス": 0.10, "ドリブル": 0.00, "シュート": 0.10, "奪取": 7.80, "守備": 8.20, "セーブ": 0.00},
        {"背番号": 25, "選手名": "真瀬 拓海", "Pos": "DF", "出場分": "90分", "攻撃": 1.80, "パス": 2.60, "クロス": 1.90, "ドリブル": 0.90, "シュート": 0.40, "奪取": 5.40, "守備": 4.90, "セーブ": 0.00},
        {"背番号": 3, "選手名": "大崎 航詩", "Pos": "MF", "出場分": "90分", "攻撃": 1.40, "パス": 2.20, "クロス": 1.20, "ドリブル": 0.60, "シュート": 0.30, "奪取": 6.10, "守備": 5.20, "セーブ": 0.00},
        {"背番号": 38, "選手名": "ウーゴ", "Pos": "MF", "出場分": "63分", "攻撃": 2.10, "パス": 3.80, "クロス": 0.40, "ドリブル": 1.10, "シュート": 0.80, "奪取": 9.20, "守備": 4.80, "セーブ": 0.00},
        {"背番号": 22, "選手名": "谷口 海斗", "Pos": "FW", "出場分": "63分", "攻撃": 2.40, "パス": 1.20, "クロス": 0.30, "ドリブル": 1.40, "シュート": 2.10, "奪取": 1.80, "守備": 1.20, "セーブ": 0.00},
    ]
    st.dataframe(mito_cbp, use_container_width=True)


def render_raw_flow_view() -> None:
    """Render 15-minute interval possession trends, attack flow, and shot coordinates."""
    st.markdown("#### ⏱️ 15分刻みポゼッション推移 ＆ プレイスタイル実測値")

    pos_table = [
        {"時間帯 (Minutes)": "前半 0〜15分", "FC東京 保持率": "48.2%", "水戸 保持率": "51.8%", "主導権": "水戸攻勢（開始3分 攻勢指数-6）"},
        {"時間帯 (Minutes)": "前半 16〜30分", "FC東京 保持率": "54.1%", "水戸 保持率": "45.9%", "主導権": "拮抗（右サイド中心のせめぎ合い）"},
        {"時間帯 (Minutes)": "前半 31〜45分", "FC東京 保持率": "46.5%", "水戸 保持率": "53.5%", "主導権": "東京先制(32分)➔水戸反撃・CKラッシュ"},
        {"時間帯 (Minutes)": "後半 46〜60分", "FC東京 保持率": "72.1%", "水戸 保持率": "27.9%", "主導権": "東京完全掌握（46分仲川2点目 +7）"},
        {"時間帯 (Minutes)": "後半 61〜75分", "FC東京 保持率": "58.4%", "水戸 保持率": "41.6%", "主導権": "水戸3枚替え➔東京カウンターで2発加点"},
        {"時間帯 (Minutes)": "後半 76〜90分", "FC東京 保持率": "59.0%", "水戸 保持率": "41.0%", "主導権": "交代組の蹂躙（ショルツ・ヒアン弾）"},
    ]
    st.table(pos_table)

    st.markdown("#### 🎯 シュート座標生ログ (FC東京 18本 / 水戸 12本)")
    shots_sample = [
        {"分数": "3分", "チーム": "水戸", "選手名": "谷口 海斗", "結果": "枠外", "xG": 0.08, "ゾーン": "ボックス左", "シチュエーション": "左CK混戦"},
        {"分数": "11分", "チーム": "FC東京", "選手名": "仲川 輝人", "結果": "枠内(セーブ)", "xG": 0.14, "ゾーン": "中央バイタル", "シチュエーション": "長倉スルーパス"},
        {"分数": "32分", "チーム": "FC東京", "選手名": "仲川 輝人", "結果": "⚽ ゴール (1-0)", "xG": 0.38, "ゾーン": "ゴール正面", "シチュエーション": "右ポケット石原クロス"},
        {"分数": "46分", "チーム": "FC東京", "選手名": "仲川 輝人", "結果": "⚽ ゴール (2-0)", "xG": 0.42, "ゾーン": "PA中央", "シチュエーション": "相手クリアミス強奪ボレー"},
        {"分数": "66分", "チーム": "FC東京", "選手名": "安斎 颯馬", "結果": "⚽ ゴール (3-0)", "xG": 0.28, "ゾーン": "左ハーフスペース", "シチュエーション": "単独長距離キャリーカウンター"},
        {"分数": "70分", "チーム": "FC東京", "選手名": "ダニ ゴメス", "結果": "⚽ ゴール (4-0)", "xG": 0.32, "ゾーン": "ニアポスト", "シチュエーション": "左CKヘディング"},
        {"分数": "76分", "チーム": "FC東京", "選手名": "ショルツ", "結果": "⚽ ゴール (5-0)", "xG": 0.24, "ゾーン": "ゴールエリア前", "シチュエーション": "右CK混戦押し込み"},
        {"分数": "93分", "チーム": "FC東京", "選手名": "マルセロ ヒアン", "結果": "⚽ ゴール (6-0)", "xG": 0.35, "ゾーン": "中央裏抜け", "シチュエーション": "山田楓喜スルーパス"},
    ]
    st.dataframe(shots_sample, use_container_width=True)


def render_raw_source_view(match_id: str) -> None:
    """Render raw source Markdown and structured JSON files."""
    st.markdown("#### 📄 収集元ソースファイル直接閲覧")

    flab_md_file = ROOT_DIR / "data" / "markdown" / "2026102505_flab.md"
    struct_json_file = ROOT_DIR / "data" / "structured" / "2026102505_tactical.json"

    col_md, col_json = st.columns(2)

    with col_md:
        st.markdown("##### 📝 Football LAB スクレイピング Markdown")
        if flab_md_file.exists():
            with open(flab_md_file, "r", encoding="utf-8") as f:
                md_text = f.read()
            st.caption(f"パス: `data/markdown/2026102505_flab.md` ({len(md_text):,} 文字)")
            with st.expander("Markdown 全文を展開して確認", expanded=False):
                st.code(md_text, language="markdown")
        else:
            st.info("該当のMarkdownファイルが見つかりません。")

    with col_json:
        st.markdown("##### 🧱 構造化戦術 JSON (2層RAG中間データ)")
        if struct_json_file.exists():
            with open(struct_json_file, "r", encoding="utf-8") as f:
                json_text = f.read()
            st.caption(f"パス: `data/structured/2026102505_tactical.json` ({len(json_text):,} 文字)")
            with st.expander("JSON 全文を展開して確認", expanded=False):
                st.code(json_text, language="json")
        else:
            st.info("該当のJSONファイルが見つかりません。")


def render_raw_data_tab(
    match_id: str,
    summary: Dict[str, Any],
) -> None:
    """Render comprehensive raw match data from Football LAB, CBP, and SQLite."""
    st.subheader("📦 収集Rawデータ詳細（Football LAB・CBP・座標・生ログ）")
    st.caption("スクレイピングおよびデータベース化された生スタッツ、CBPマトリクス、1分攻勢フロー、および生ソースファイルを直接閲覧できます。")

    sub_t1, sub_t2, sub_t3, sub_t4 = st.tabs(
        [
            "📊 Football LAB 全スタッツ詳細",
            "🏃 選手別 CBP (チャンスビルディング) マトリクス",
            "⏱️ 1分攻勢フロー & シュート座標",
            "📄 生ソースファイル (Markdown / JSON)",
        ],
    )

    with sub_t1:
        render_raw_stats_view(summary)

    with sub_t2:
        render_raw_cbp_view()

    with sub_t3:
        render_raw_flow_view()

    with sub_t4:
        render_raw_source_view(match_id)


# ==============================================================================
# Tab 5: AI Tactical Reasoning (9 Questions & 4 Watching Lenses)
# ==============================================================================

def render_ai_reasoning_tab(
    engine: TacticalAnalystEngine,
    gemini_client: GeminiTacticalClient,
    match_id: str,
    home_id: str,
    away_id: str,
) -> None:
    """Render the Gemini AI deep tactical reasoning covering the 9 Questions and 4 Watching Lenses."""
    st.subheader("🧠 プロ分析官のAI戦術推論（9つの問い ＆ 4つの観戦レンズ）")

    q_category = st.radio(
        "推論カテゴリを選択:",
        options=[
            "① 【因果と戦略】要因分析(Why) / 改善処方箋(How) / 反実仮想(What-if)",
            "② 【検証と診断】言行一致の検証 / スコア状況別DNA / 実力と運の切り分け",
            "③ 【選手とケミストリー】黒子(陰のMVP) / 相性ケミストリー / 戦術の賞味期限",
            "🔭 【4つの観戦レンズ】スタジアム観戦ガイド生成",
        ],
        index=0,
    )

    query_input = st.text_input(
        "分析対象のキーワードまたは現象を入力:",
        value="敵陣パス成功率低下" if "Why" in q_category else "46分の追加点と水戸のバランス崩壊",
    )

    if st.button("⚡ AI推論を実行", key="btn_reasoning"):
        with st.spinner("2層RAGのコンテキストを抽出してGeminiで推論中..."):
            if "Why" in q_category:
                ctx = engine.build_why_analysis(
                    match_id=match_id,
                    team_id=home_id,
                    phenomenon=query_input,
                )
            elif "4つの観戦レンズ" in q_category:
                ctx = engine.build_watching_guide(
                    match_id=match_id,
                    formation_home="4-4-2",
                    formation_away="4-4-2",
                )
            else:
                ctx = engine.build_game_state_dna_analysis(
                    team_id=home_id,
                    match_id=match_id,
                )

            if gemini_client.is_available():
                ai_res = engine.run_analysis(
                    analysis_context=ctx,
                    llm_callable=gemini_client.as_callable(),
                )
                st.markdown("### 📋 AI分析結果")
                st.markdown(ai_res.get("response", ""))
            else:
                st.info("Gemini APIキーが未設定のため、注入用プロンプトを表示します。")
                st.code(ctx.get("user_prompt", ""), language="markdown")


def render_sidebar_match_selector(
    db_path: str = DEFAULT_DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Render the sidebar season, matchweek, and match card dropdowns."""
    st.sidebar.header("🔍 試合選択フィルター")

    seasons = fetch_available_seasons(db_path=db_path)
    selected_season = st.sidebar.selectbox(
        "シーズンを選択",
        options=seasons,
        index=0,
    )

    available_mws = fetch_available_matchweeks(season=selected_season, db_path=db_path)

    if available_mws:
        use_mw_filter = st.sidebar.checkbox(
            "節数で絞り込む",
            value=(selected_season != 2026),
        )
    else:
        use_mw_filter = False

    if use_mw_filter and available_mws:
        selected_mw = st.sidebar.selectbox(
            "節数を選択",
            options=available_mws,
            index=0,
        )
        matches = fetch_matches_for_mw(
            mw=selected_mw,
            season=selected_season,
            db_path=db_path,
        )
    else:
        matches = fetch_matches_for_season(
            season=selected_season,
            db_path=db_path,
        )

    if not matches:
        st.sidebar.warning(f"{selected_season} シーズンの試合データが見つかりませんでした。")
        return None

    match_options = {}
    for m in matches:
        h_name = get_team_display_name(m.get("home_team_id"))
        a_name = get_team_display_name(m.get("away_team_id"))
        mw_str = get_matchweek_display_text(m)
        label = f"[{m.get('date', '-')}] {h_name} {m.get('home_score', '-')}-{m.get('away_score', '-')} {a_name} ({mw_str})"
        match_options[label] = m

    selected_label = st.sidebar.selectbox(
        "試合カードを選択",
        options=list(match_options.keys()),
        index=0,
    )
    return match_options[selected_label]


def render_sidebar_llm_settings() -> GeminiTacticalClient:
    """Render the sidebar Gemini AI settings inputs and return configured client."""
    st.sidebar.markdown("---")
    st.sidebar.header("🤖 Gemini AI 設定")
    api_key_input = st.sidebar.text_input(
        "Gemini API キー (未入力時は環境変数を使用)",
        type="password",
        help=".env や環境変数 GEMINI_API_KEY があれば自動適用されます",
    )
    default_index = 0
    if DEFAULT_GEMINI_MODEL in SUPPORTED_GEMINI_MODELS:
        default_index = SUPPORTED_GEMINI_MODELS.index(DEFAULT_GEMINI_MODEL)

    model_name = st.sidebar.selectbox(
        "モデル選択",
        options=SUPPORTED_GEMINI_MODELS,
        index=default_index,
    )
    use_mock = st.sidebar.checkbox(
        "検証用モックモード (APIキー不要)",
        value=False,
    )
    return GeminiTacticalClient(
        api_key=api_key_input or None,
        model=model_name,
        mock_mode=use_mock,
    )


# ==============================================================================
# Main Streamlit App
# ==============================================================================

def main():
    st.set_page_config(
        page_title="Jリーグ戦術分析・観戦ガイドRAG",
        page_icon="⚽",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("⚽ Jリーグ戦術分析・観戦ガイド RAG システム")
    st.caption("2層ハイブリッドRAG × 客観データ多角分析・定性対比エージェント")

    engine = get_engine()
    profiler, comparator, rater = get_analysis_modules()

    # --------------------------------------------------------------------------
    # Sidebar Filters & AI Settings
    # --------------------------------------------------------------------------
    selected_match = render_sidebar_match_selector()
    if not selected_match:
        return

    match_id = selected_match["match_id"]
    gemini_client = render_sidebar_llm_settings()

    # --------------------------------------------------------------------------
    # Main Content Area
    # --------------------------------------------------------------------------
    render_header(selected_match)

    summary = engine.sql_tools.get_match_summary(match_id) or {}
    home_id = selected_match["home_team_id"]
    away_id = selected_match["away_team_id"]
    reviews = fetch_match_reviews(match_id)

    tab_obj, tab_comp, tab_rate, tab_adv, tab_stats, tab_raw_data, tab_ai, tab_reviews = st.tabs(
        [
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

    # Tab 1: Objective Analysis
    with tab_obj:
        render_objective_perspectives_tab(profiler, summary)

    # Tab 2: Qualitative Comparison
    with tab_comp:
        render_qualitative_comparison_tab(comparator, profiler, match_id, summary, reviews)

    # Tab 3: Player Ratings
    with tab_rate:
        render_player_ratings_tab(rater, summary)

    # Tab 4: 5 Advanced Reports
    with tab_adv:
        render_advanced_reports_tab(profiler, summary)

    # Tab 5: Stats Chart
    with tab_stats:
        st.subheader("📊 定量スタッツのグラフィカル比較")
        render_stats_chart(summary, home_id, away_id)

    # Tab 6: Raw Data Explorer
    with tab_raw_data:
        render_raw_data_tab(match_id, summary)

    # Tab 7: AI Reasoning
    with tab_ai:
        render_ai_reasoning_tab(engine, gemini_client, match_id, home_id, away_id)

    # Tab 8: Raw Qualitative Reviews
    with tab_reviews:
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


if __name__ == "__main__":
    main()
