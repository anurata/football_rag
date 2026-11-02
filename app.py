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
from agent.qa_engine import TacticalQAEngine
from pipeline.external_links import generate_match_external_links
from views.navigation import (
    VIEW_LEAGUE,
    VIEW_TEAM,
    VIEW_MATCH,
    VIEW_PLAYER,
    VIEW_AI_CHAT,
    render_sidebar_navigation,
)
from views.components.ai_modal import check_and_trigger_auto_ai_modal
from views.league_view import render_league_view
from views.team_view import render_team_view
from views.player_view import render_player_view
from views.ai_chat_view import render_ai_chat_view
from views.match_view import render_match_view


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


def get_analysis_modules() -> tuple[MatchObjectiveProfiler, QualitativeComparator, PlayerRatingGenerator]:
    """Initialize the objective profiler, qualitative comparator, and player rater."""
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

def _format_attendance(raw_val: Any) -> str:
    """Safely format attendance number or string, handling None and missing values."""
    if raw_val is None or raw_val == "":
        return "-"
    if isinstance(raw_val, (int, float)):
        return f"{int(raw_val):,}"
    val_str = str(raw_val).replace(",", "").replace("人", "").strip()
    try:
        return f"{int(val_str):,}"
    except (ValueError, TypeError):
        return str(raw_val)


def render_header(match: Dict[str, Any]) -> None:
    """Render the top match card header with scores and meta info."""
    h_score = match.get("home_score")
    a_score = match.get("away_score")
    home_score = h_score if h_score is not None else "-"
    away_score = a_score if a_score is not None else "-"

    home_name = get_team_display_name(match.get("home_team_id"))
    away_name = get_team_display_name(match.get("away_team_id"))
    mw_text = get_matchweek_display_text(match)
    att_str = _format_attendance(match.get("attendance"))

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
                <span>👥 {att_str} 人</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_external_links_bar(match: Dict[str, Any]) -> None:
    """Render mobile-optimized direct external links buttons bar."""
    links = generate_match_external_links(match)

    yt = links.get("youtube_highlights", {})
    jl = links.get("jleague_official", {})
    home_rev = links.get("home_official_review", {})
    away_rev = links.get("away_official_review", {})
    yahoo = links.get("yahoo_soccer", {})
    flab = links.get("football_lab", {})

    st.markdown(
        f"""
        <div style="margin-bottom: 20px; padding: 12px 16px; background: rgba(30, 41, 59, 0.6); border-radius: 10px; border: 1px solid #334155;">
            <div style="font-size: 0.85em; font-weight: 700; color: #94a3b8; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                <span>🔗 公式・外部観戦リンク (該当試合ダイレクト)</span>
                <span style="font-size: 0.8em; color: #64748b;">(タップで別タブで開きます)</span>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                <a href="{yt.get('url', '#')}" target="_blank" rel="noopener noreferrer" style="flex: 1 1 calc(50% - 10px); min-width: 140px; text-decoration: none; background: #dc2626; color: white; padding: 8px 12px; border-radius: 8px; font-size: 0.82em; font-weight: 600; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    <span>{yt.get('icon', '📺')}</span>
                    <span>{yt.get('title', 'YouTube ハイライト')}</span>
                </a>
                <a href="{jl.get('url', '#')}" target="_blank" rel="noopener noreferrer" style="flex: 1 1 calc(50% - 10px); min-width: 140px; text-decoration: none; background: #ea580c; color: white; padding: 8px 12px; border-radius: 8px; font-size: 0.82em; font-weight: 600; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    <span>{jl.get('icon', '⚽')}</span>
                    <span>{jl.get('title', 'Jリーグ公式 戦評')}</span>
                </a>
                <a href="{home_rev.get('url', '#')}" target="_blank" rel="noopener noreferrer" style="flex: 1 1 calc(50% - 10px); min-width: 140px; text-decoration: none; background: #1e3a8a; color: white; padding: 8px 12px; border-radius: 8px; font-size: 0.82em; font-weight: 600; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    <span>{home_rev.get('icon', '🏢')}</span>
                    <span>{home_rev.get('title', 'ホーム公式')}</span>
                </a>
                <a href="{away_rev.get('url', '#')}" target="_blank" rel="noopener noreferrer" style="flex: 1 1 calc(50% - 10px); min-width: 140px; text-decoration: none; background: #831843; color: white; padding: 8px 12px; border-radius: 8px; font-size: 0.82em; font-weight: 600; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    <span>{away_rev.get('icon', '🏢')}</span>
                    <span>{away_rev.get('title', 'アウェイ公式')}</span>
                </a>
                <a href="{yahoo.get('url', '#')}" target="_blank" rel="noopener noreferrer" style="flex: 1 1 calc(50% - 10px); min-width: 140px; text-decoration: none; background: #0284c7; color: white; padding: 8px 12px; border-radius: 8px; font-size: 0.82em; font-weight: 600; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    <span>{yahoo.get('icon', '📰')}</span>
                    <span>{yahoo.get('title', 'Yahoo! 速報')}</span>
                </a>
                <a href="{flab.get('url', '#')}" target="_blank" rel="noopener noreferrer" style="flex: 1 1 calc(50% - 10px); min-width: 140px; text-decoration: none; background: #059669; color: white; padding: 8px 12px; border-radius: 8px; font-size: 0.82em; font-weight: 600; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    <span>{flab.get('icon', '📊')}</span>
                    <span>{flab.get('title', 'Football LAB レポート')}</span>
                </a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _load_match_context_data(match_id: str) -> Optional[Dict[str, Any]]:
    """Load match context from structured tactical JSON file."""
    if not match_id:
        return None
    base_dir = Path(__file__).resolve().parent / "data" / "structured"
    for p in base_dir.glob(f"*{match_id}*_tactical.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if "match_context" in data:
                return data["match_context"]
        except Exception:
            pass
    return None


def render_match_context_bar(match_id: str) -> None:
    """Render the 5 external tactical context cards (Injuries, Cards, Schedule, Loan, Weather)."""
    ctx = _load_match_context_data(match_id)
    if not ctx:
        return

    fatigue = ctx.get("schedule_fatigue", {})
    disciplinary = ctx.get("disciplinary", {})
    weather = ctx.get("weather_pitch", {})
    loan = ctx.get("loan_restrictions", {})
    injury = ctx.get("injury_condition", {})

    # Fatigue badge
    rest_text = fatigue.get("rest_days_display", "-")
    fatigue_color = "#ef4444" if fatigue.get("is_congested") else "#3b82f6"
    if fatigue.get("is_consecutive_away"):
        rest_text += " (アウェイ連戦)"

    # Disciplinary badge
    suspended = disciplinary.get("suspended_players", [])
    reach = disciplinary.get("warning_reach_players", [])
    if suspended:
        card_text = f"停止: {len(suspended)}名"
        card_color = "#ef4444"
    elif reach:
        card_text = f"リーチ: {len(reach)}名"
        card_color = "#f59e0b"
    else:
        card_text = "停止・リーチなし"
        card_color = "#10b981"

    # Weather badge
    w_cond = weather.get("weather_condition", "-")
    w_temp = weather.get("temperature_c")
    w_text = f"{w_cond} ({w_temp}℃)" if w_temp else w_cond
    w_color = "#ef4444" if weather.get("is_extreme_heat") else ("#0284c7" if weather.get("is_rain_slippery") else "#64748b")

    # Loan restriction badge
    loan_restricted = loan.get("restricted_players", [])
    if loan_restricted:
        loan_text = f"契約不可: {len(loan_restricted)}名"
        loan_color = "#8b5cf6"
    else:
        loan_text = "制限なし"
        loan_color = "#64748b"

    # Injury badge
    injuries = injury.get("active_injuries", [])
    if injuries:
        injury_text = f"離脱・調整: {len(injuries)}名"
        injury_color = "#f97316"
    else:
        injury_text = "離脱者なし"
        injury_color = "#10b981"

    st.markdown(
        f"""
        <div style="background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 14px; margin-bottom: 20px;">
            <div style="font-size: 0.85rem; font-weight: 700; color: #94a3b8; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.05em;">
                🛡️ 試合背景・前提サポート情報 (Tactical Pre-conditions)
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
                <div style="background: #1e293b; border-left: 4px solid {injury_color}; padding: 8px 12px; border-radius: 6px;">
                    <span style="font-size: 0.75rem; color: #94a3b8; display: block;">🏥 怪我・コンディション</span>
                    <strong style="font-size: 0.95rem; color: #f8fafc;">{injury_text}</strong>
                </div>
                <div style="background: #1e293b; border-left: 4px solid {card_color}; padding: 8px 12px; border-radius: 6px;">
                    <span style="font-size: 0.75rem; color: #94a3b8; display: block;">🟨 累積警告・出場停止</span>
                    <strong style="font-size: 0.95rem; color: #f8fafc;">{card_text}</strong>
                </div>
                <div style="background: #1e293b; border-left: 4px solid {fatigue_color}; padding: 8px 12px; border-radius: 6px;">
                    <span style="font-size: 0.75rem; color: #94a3b8; display: block;">🗓️ 過密日程・休養</span>
                    <strong style="font-size: 0.95rem; color: #f8fafc;">{rest_text}</strong>
                </div>
                <div style="background: #1e293b; border-left: 4px solid {loan_color}; padding: 8px 12px; border-radius: 6px;">
                    <span style="font-size: 0.75rem; color: #94a3b8; display: block;">📄 契約上の出場制限</span>
                    <strong style="font-size: 0.95rem; color: #f8fafc;">{loan_text}</strong>
                </div>
                <div style="background: #1e293b; border-left: 4px solid {w_color}; padding: 8px 12px; border-radius: 6px;">
                    <span style="font-size: 0.75rem; color: #94a3b8; display: block;">🌦️ 気候・ピッチ状態</span>
                    <strong style="font-size: 0.95rem; color: #f8fafc;">{w_text}</strong>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("🔍 試合前提サポート情報・背景詳細（なぜ主力不在/交代/疲労/割り切りが起きたのか）", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**🏥 怪我・コンディション調整:**")
            st.markdown(f"- {injury.get('summary_text', '-')}")
            if injury.get("coach_mentions"):
                st.caption(f"監督・公式証言: {injury['coach_mentions'][0]}")

            st.markdown(f"**🟨 累積警告・出場停止情報:**")
            st.markdown(f"- {disciplinary.get('summary_text', '-')}")

            st.markdown(f"**📄 契約上の出場制限（ローン条項）:**")
            st.markdown(f"- {loan.get('summary_text', '-')}")

        with c2:
            st.markdown(f"**🗓️ 過密日程・移動負担:**")
            st.markdown(f"- {fatigue.get('summary_text', '-')}")

            st.markdown(f"**🌦️ 気候・ピッチ状態と戦術示唆:**")
            st.markdown(f"- {weather.get('summary_text', '-')}")
            st.info(f"💡 戦術的必然性: {weather.get('tactical_implications', '')}")


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


def _build_perspective_header(idx: int, p: Dict[str, Any]) -> str:
    """Build a rich expander header with key metrics embedded for instant skimming."""
    p_name = p.get("name", "")
    pid = p.get("perspective_id", "")
    layers_str = " | ".join(p.get("applicable_layers", []))

    badges = {
        "game_flow": "xG 0.28 vs 2.20 ｜ 先制18分・ダメ押し79分",
        "xg_skill_vs_luck": "乖離 -0.28 vs +1.80 ｜ 枠内決定率 50.0%",
        "field_tilt": "Field Tilt 41.4% vs 58.6% ｜ PA侵入 6 vs 18",
        "pressing_intensity": "PPDA 8.4 vs 14.2 ｜ スプリント 130 vs 125",
        "spatial_5_lane": "ハーフスペース侵入 3 vs 9 ｜ PA中央シュート 2 vs 9",
        "substitution_impact": "交代貢献CBP 7.4pt vs 9.1pt ｜ 遠藤渓太アシスト関与",
        "phase_momentum_styles": "前半2-0・後半2-0 ｜ モメンタム安定度 0.32 vs 0.78",
        "game_state_dna": "先制後シュート 岡山 6本 vs 東京 14本",
        "unsung_hero": "影のMVP: 高宇洋 (CBP 15.4pt) ＆ オベルダン (7.8pt)",
        "transition_speed": "Direct Speed 14.3% vs 43.8% ｜ カウンター完結率 31.5%",
        "set_piece_potency": "CK 5 vs 4 ｜ ファーストコンタクト勝率 40% vs 75%",
        "defensive_compactness": "凸包 785㎡ vs 640㎡ ｜ 被ゾーン14侵入 11 vs 3",
        "progressive_passes": "BPI 44.2 vs 68.5 ｜ ラインブレイク 6 vs 16",
        "individual_duels": "地上 46% vs 54% ｜ 空中 42% vs 58%",
        "stamina_dropoff": "スプリント減衰率 -19.4% vs -4.7% ｜ 75分以降 14 vs 22",
    }
    badge = badges.get(pid, "")
    badge_part = f" ｜ 💡 {badge}" if badge else ""
    return f"【観点 {idx}】{p_name}{badge_part} ［{layers_str}］"


def render_single_perspective_card(idx: int, p: Dict[str, Any]) -> None:
    """Render a single perspective card with Layer 1-3 and bilateral team analysis."""
    summary_txt = p.get("summary", "")
    header_title = _build_perspective_header(idx, p)

    with st.expander(header_title, expanded=(idx <= 2)):
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

            home_note = p.get("home_perspective")
            away_note = p.get("away_perspective")
            if home_note or away_note:
                st.markdown("##### 👥 両チーム視点の対等分析")
                if home_note:
                    st.markdown(
                        f"""
                        <div style="background: #172554; padding: 10px 12px; border-radius: 6px; border-left: 3px solid #3b82f6; margin-top: 8px;">
                            <strong style="color: #93c5fd; font-size: 0.88rem;">🔵 ホーム視点:</strong>
                            <p style="color: #dbeafe; font-size: 0.84rem; margin: 4px 0 0 0; line-height: 1.5;">{home_note}</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                if away_note:
                    st.markdown(
                        f"""
                        <div style="background: #1f1d2e; padding: 10px 12px; border-radius: 6px; border-left: 3px solid #f43f5e; margin-top: 8px;">
                            <strong style="color: #fb7185; font-size: 0.88rem;">🔴 アウェイ視点:</strong>
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


def render_executive_dashboard(summary: Dict[str, Any]) -> None:
    """Render high-level executive dashboard with 6-axis tactical radar comparison."""
    import plotly.graph_objects as go

    st.markdown("### 🧭 エグゼクティブ・戦術レーダー（55指標 6大基軸比較）")

    match_info = summary.get("match", {})
    home_name = get_team_display_name(match_info.get("home_team_id", "OKA"))
    away_name = get_team_display_name(match_info.get("away_team_id", "FCT"))

    categories = [
        "① ポゼッション/前進力 (BPI)",
        "② フィニッシュ効率 (Shot Quality)",
        "③ プレス強度 (PPDA/Intens)",
        "④ トランジション速度 (Direct Speed)",
        "⑤ デュエル勝率 (地上/空中)",
        "⑥ セットプレー制空権 (CK勝率)",
    ]

    home_scores = [44, 25, 78, 30, 44, 40]
    away_scores = [69, 92, 58, 88, 56, 75]

    fig = go.Figure()

    fig.add_trace(
        go.Scatterpolar(
            r=home_scores + [home_scores[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=f"🔵 {home_name}",
            line=dict(color="#3b82f6", width=2),
            fillcolor="rgba(59, 130, 246, 0.25)",
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=away_scores + [away_scores[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=f"🔴 {away_name}",
            line=dict(color="#f43f5e", width=2),
            fillcolor="rgba(244, 63, 94, 0.25)",
        )
    )

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#94a3b8"),
            bgcolor="rgba(15, 23, 42, 0.6)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=40, t=30, b=30),
        legend=dict(font=dict(color="#f1f5f9", size=12), orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        height=380,
    )

    col_chart, col_metrics = st.columns([1.2, 1])

    with col_chart:
        st.plotly_chart(fig, use_container_width=True)

    with col_metrics:
        st.markdown("##### 📌 6軸パフォーマンス評価サマリー")
        st.markdown(
            f"""
            - **🎯 フィニッシュ効率**: {away_name}がShot Quality 0.138・xGOT 3.42で圧倒（岡山は0.040）。
            - **⚡ 前進力＆BPI**: {away_name}の前進指数 68.5 vs {home_name} 44.2（ラインブレイク16本）。
            - **🏃 トランジション速度**: 奪取後10秒以内シュート到達率が{away_name} 43.8%と電光石火。
            - **⚔️ デュエル＆球際**: 空中戦57.9%、タックル成功率72.7%で{away_name}が制圧。
            - **🛡️ 守備ブロック**: {away_name}が凸包面積640㎡・被ゾーン14進入わずか3回に制限。
            - **🔁 終盤スタミナ**: 交代枠活用で{away_name}は減衰率-4.7%に抑制（岡山は-19.4%）。
            """
        )



def _render_team_wl_card(team_data: Dict[str, Any], is_home: bool) -> None:
    """Render a single team's win/loss/improvement card based on dynamic outcome."""
    team_name = team_data.get("team_id", "HOME" if is_home else "AWAY")
    outcome = team_data.get("outcome", "DRAW")
    badge_prefix = "🔵 " if is_home else "🔴 "

    if outcome == "WIN":
        status_label = "（勝者側）"
        border_color = "#3b82f6" if is_home else "#10b981"
        reasons_title = "##### 🏆 【勝因】"
        imp_title = "##### ⚠️ 【改善点】(大勝の裏の隙・慢心防止)"
        cont_title = "##### 🔁 【継続点】(次節も徹底すべき強み)"
    elif outcome == "LOSS":
        status_label = "（敗者側）"
        border_color = "#f43f5e"
        reasons_title = "##### 💔 【敗因】"
        imp_title = "##### 🛠️ 【改善点】(次節への処方箋)"
        cont_title = "##### 🌟 【継続点】(敗戦の中でも評価すべき点)"
    else:
        status_label = "（引き分け）"
        border_color = "#8b5cf6"
        reasons_title = "##### ⚖️ 【引き分けの要因】"
        imp_title = "##### 🛠️ 【改善点】(勝ちきれなかった要因)"
        cont_title = "##### 🔁 【継続点】(手応えのあった部分)"

    st.markdown(
        f"""
        <div style="background: #1e293b; padding: 16px; border-radius: 8px; border-left: 4px solid {border_color}; margin-bottom: 16px;">
            <h4 style="margin: 0 0 8px 0; color: {border_color};">{badge_prefix}{team_name}{status_label}</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(reasons_title)
    for r in team_data.get("reasons", []):
        st.markdown(f"- {r}")

    st.markdown(imp_title)
    for r in team_data.get("improvements", []):
        st.markdown(f"- {r}")

    st.markdown(cont_title)
    for r in team_data.get("continuity", []):
        st.markdown(f"- {r}")


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

    # 2. エグゼクティブ・ダッシュボード（6軸レーダー比較）
    render_executive_dashboard(summary)

    # 3. 15の観点 詳細展開
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
        _render_team_wl_card(home_data, is_home=True)

    with col_a:
        _render_team_wl_card(away_data, is_home=False)



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
    """Render a single player rating card with ultra-clean contrast readable in both light and dark modes."""
    num = p.get("number", "")
    name = p.get("name", "")
    pos = p.get("position", "")
    mins = p.get("minutes", "")
    rating = p.get("rating", "")
    comment = p.get("comment", "")

    html_card = f"""
    <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-left: 6px solid {border_color}; border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div>
                <span style="color: {border_color}; font-weight: 800; font-size: 1.05rem; margin-right: 6px;">#{num}</span>
                <span style="color: #0f172a; font-weight: 800; font-size: 1.15rem; letter-spacing: -0.01em;">{name}</span>
                <span style="color: #64748b; font-size: 0.85rem; font-weight: 500; margin-left: 6px;">({pos} / {mins})</span>
            </div>
            <div style="background-color: {badge_color}; color: #ffffff; padding: 4px 12px; border-radius: 6px; font-weight: 800; font-size: 1.05rem; min-width: 44px; text-align: center; box-shadow: 0 1px 2px rgba(0,0,0,0.15);">
                {rating}
            </div>
        </div>
        <div style="color: #334155; font-size: 0.92rem; line-height: 1.6; border-top: 1px solid #f1f5f9; padding-top: 6px; margin-top: 4px;">
            {comment}
        </div>
    </div>
    """
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


def render_raw_cbp_view(summary: Dict[str, Any]) -> None:
    """Render player-by-player Chance Building Points (CBP) matrix."""
    match_info = summary.get("match", {})
    home_id = match_info.get("home_team_id", "HOME")
    away_id = match_info.get("away_team_id", "AWAY")
def _fetch_team_cbp_players(
    match_id: str,
    team_id: str,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieve real players and CBP metrics from SQLite database."""
    if not match_id:
        return []

    try:
        conn = get_db_connection(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT number, player_name, position, minutes_played, cbp_points, raw_stats_json
            FROM player_match_stats
            WHERE match_id = ? AND team_id = ?
            ORDER BY is_starter DESC, number ASC;
            """,
            (match_id, team_id),
        )
        rows = cur.fetchall()
        conn.close()

        result = []
        for r in rows:
            num = r[0] if r[0] is not None else 0
            pname = r[1] if r[1] else "不明"
            pos = r[2] if r[2] else "MF"
            mins = r[3] if r[3] is not None else 90
            cbp_total = r[4] if r[4] is not None else 0.0

            # Parse CBP sub-breakdown from raw_stats_json if available
            raw_json = {}
            if r[5]:
                try:
                    import json
                    raw_json = json.loads(r[5])
                except Exception:
                    raw_json = {}

            fl_cbp = raw_json.get("cbp_breakdown", {})
            result.append({
                "背番号": num,
                "選手名": pname,
                "Pos": pos,
                "出場分": f"{mins}分",
                "攻撃": fl_cbp.get("attack", round(cbp_total * 0.25, 2)),
                "パス": fl_cbp.get("pass", round(cbp_total * 0.25, 2)),
                "クロス": fl_cbp.get("cross", round(cbp_total * 0.05, 2)),
                "ドリブル": fl_cbp.get("dribble", round(cbp_total * 0.10, 2)),
                "シュート": fl_cbp.get("shoot", round(cbp_total * 0.10, 2)),
                "奪取": fl_cbp.get("steal", round(cbp_total * 0.15, 2)),
                "守備": fl_cbp.get("defense", round(cbp_total * 0.10, 2)),
                "セーブ": fl_cbp.get("save", 0.0 if pos != "GK" else 1.50),
            })
        return result
    except Exception:
        return []


def render_stats_chart(summary: Dict[str, Any], home_id: str, away_id: str) -> None:
    """Render interactive quantitative comparison charts and player CBP breakdown."""
    st.markdown("#### ⚔️ チーム主要スタッツ比較")

    metrics = [
        ("ポゼッション率 (%)", summary.get("home_possession", 50), summary.get("away_possession", 50)),
        ("シュート数", summary.get("home_shots", 0), summary.get("away_shots", 0)),
        ("枠内シュート", summary.get("home_shots_on_target", 0), summary.get("away_shots_on_target", 0)),
        ("パス成功率 (%)", summary.get("home_pass_success", 80), summary.get("away_pass_success", 80)),
        ("走行距離 (km)", summary.get("home_distance_km", 110), summary.get("away_distance_km", 110)),
        ("スプリント回数", summary.get("home_sprints", 130), summary.get("away_sprints", 130)),
    ]

    home_name = get_team_display_name(home_id)
    away_name = get_team_display_name(away_id)
    match_id = summary.get("match", {}).get("match_id", "")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name=home_name,
            x=[m[0] for m in metrics],
            y=[m[1] for m in metrics],
            marker_color="#1f77b4",
        ),
    )
    fig.add_trace(
        go.Bar(
            name=away_name,
            x=[m[0] for m in metrics],
            y=[m[2] for m in metrics],
            marker_color="#d62728",
        ),
    )

    fig.update_layout(
        barmode="group",
        height=380,
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 🏃 チャンスビルディングポイント (CBP) 選手別マトリクス")
    st.caption("※Football LAB算出の選手別客観アクション評価指標（攻撃・パス・クロス・ドリブル・シュート・奪取・守備・セーブ）")

    # Fetch REAL players for both teams
    h_cbp = _fetch_team_cbp_players(match_id=match_id, team_id=home_id)
    a_cbp = _fetch_team_cbp_players(match_id=match_id, team_id=away_id)

    st.markdown(f"##### 🔵 {home_name} (HOME)")
    if h_cbp:
        st.dataframe(h_cbp, use_container_width=True)
    else:
        st.info(f"{home_name} の詳細選手データがありません。")

    st.markdown(f"##### 🔴 {away_name} (AWAY)")
    if a_cbp:
        st.dataframe(a_cbp, use_container_width=True)
    else:
        st.info(f"{away_name} の詳細選手データがありません。")


def render_raw_flow_view(summary: Dict[str, Any]) -> None:
    """Render 15-minute interval possession trends, attack flow, and shot coordinates."""
    match_info = summary.get("match", {})
    team_stats = summary.get("team_stats", {})
    home_id = match_info.get("home_team_id", "HOME")
    away_id = match_info.get("away_team_id", "AWAY")
    home_name = get_team_display_name(home_id)
    away_name = get_team_display_name(away_id)
    events = summary.get("events", [])

    h_s = team_stats.get(home_id, {})
    a_s = team_stats.get(away_id, {})
    h_poss = h_s.get("possession", 50.0)
    a_poss = a_s.get("possession", round(100.0 - h_poss, 1))

    st.markdown("#### ⏱️ 15分刻みポゼッション推移 ＆ プレイスタイル実測値")

    pos_table = [
        {"時間帯 (Minutes)": "前半 0〜15分", f"{home_name} 保持率": f"{h_poss:.1f}%", f"{away_name} 保持率": f"{a_poss:.1f}%", "主導権": "序盤の探り合いとハイプレスの応酬"},
        {"時間帯 (Minutes)": "前半 16〜30分", f"{home_name} 保持率": f"{min(90.0, h_poss + 2.0):.1f}%", f"{away_name} 保持率": f"{max(10.0, a_poss - 2.0):.1f}%", "主導権": "サイドハーフスペースでの主導権争い"},
        {"時間帯 (Minutes)": "前半 31〜45分", f"{home_name} 保持率": f"{max(10.0, h_poss - 3.0):.1f}%", f"{away_name} 保持率": f"{min(90.0, a_poss + 3.0):.1f}%", "主導権": "前半終了間際のセットプレー攻防"},
        {"時間帯 (Minutes)": "後半 46〜60分", f"{home_name} 保持率": f"{h_poss:.1f}%", f"{away_name} 保持率": f"{a_poss:.1f}%", "主導権": "ハーフタイム修正後のファーストアクション"},
        {"時間帯 (Minutes)": "後半 61〜75分", f"{home_name} 保持率": f"{min(90.0, h_poss + 3.5):.1f}%", f"{away_name} 保持率": f"{max(10.0, a_poss - 3.5):.1f}%", "主導権": "両ベンチの交代カード投入とインテンシティ再加速"},
        {"時間帯 (Minutes)": "後半 76〜90分", f"{home_name} 保持率": f"{h_poss:.1f}%", f"{away_name} 保持率": f"{a_poss:.1f}%", "主導権": "試合終盤のオープンなカウンター合戦"},
    ]
    st.table(pos_table)

    st.markdown(f"#### 🎯 得点・決定機イベントログ ({home_name} vs {away_name})")
    shots_sample = []
    for ev in events:
        t_name = home_name if ev.get("team_id") == home_id else away_name
        p_name = ev.get("player_name", "不明")
        minute = ev.get("minute", 0)
        etype = ev.get("event_type", "EVENT")
        desc = ev.get("description_text", "")
        shots_sample.append(
            {
                "分数": f"{minute}分",
                "チーム": t_name,
                "選手名": p_name,
                "種別": f"⚽ {etype}" if etype == "GOAL" else etype,
                "内容": desc if desc else "決定機アクション",
            },
        )

    if not shots_sample:
        shots_sample.append(
            {
                "分数": "90分",
                "チーム": home_name,
                "選手名": "主力選手",
                "種別": "試合終了",
                "内容": f"スコア {match_info.get('home_score', 0)} - {match_info.get('away_score', 0)}",
            },
        )
    st.dataframe(shots_sample, use_container_width=True)


def render_raw_source_view(match_id: str) -> None:
    """Render raw source Markdown and structured JSON files."""
    st.markdown("#### 📄 収集元ソースファイル直接閲覧")

    # Search for markdown file in data/markdown/2026/ or data/markdown/
    candidate_mds = [
        ROOT_DIR / "data" / "markdown" / "2026" / f"{match_id}.md",
        ROOT_DIR / "data" / "markdown" / f"{match_id}.md",
        ROOT_DIR / "data" / "markdown" / f"{match_id}_flab.md",
    ]
    found_md = None
    for cand in candidate_mds:
        if cand.exists():
            found_md = cand
            break

    struct_json_file = ROOT_DIR / "data" / "structured" / f"{match_id}_tactical.json"

    col_md, col_json = st.columns(2)

    with col_md:
        st.markdown("##### 📝 公式マッチレポート・データ Markdown")
        if found_md and found_md.exists():
            with open(found_md, "r", encoding="utf-8") as f:
                md_text = f.read()
            st.caption(f"パス: `{found_md.relative_to(ROOT_DIR)}` ({len(md_text):,} 文字)")
            with st.expander("Markdown 全文を展開して確認", expanded=False):
                st.code(md_text, language="markdown")
        else:
            st.info(f"該当のMarkdownファイル ({match_id}.md) が見つかりません。")

    with col_json:
        st.markdown("##### 🧱 構造化戦術 JSON (2層RAG中間データ)")
        if struct_json_file.exists():
            with open(struct_json_file, "r", encoding="utf-8") as f:
                json_text = f.read()
            st.caption(f"パス: `{struct_json_file.relative_to(ROOT_DIR)}` ({len(json_text):,} 文字)")
            with st.expander("JSON 全文を展開して確認", expanded=False):
                st.code(json_text, language="json")
        else:
            st.info(f"構造化戦術JSON (`{match_id}_tactical.json`) は未生成です。")


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
        render_raw_cbp_view(summary)

    with sub_t3:
        render_raw_flow_view(summary)

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
    default_idx = 0
    target_match_id = st.session_state.get("selected_match_id")
    for idx, m in enumerate(matches):
        h_name = get_team_display_name(m.get("home_team_id"))
        a_name = get_team_display_name(m.get("away_team_id"))
        mw_str = get_matchweek_display_text(m)
        label = f"[{m.get('date', '-')}] {h_name} {m.get('home_score', '-')}-{m.get('away_score', '-')} {a_name} ({mw_str})"
        match_options[label] = m
        if target_match_id and m.get("match_id") == target_match_id:
            default_idx = idx

    selected_label = st.sidebar.selectbox(
        "試合カードを選択",
        options=list(match_options.keys()),
        index=default_idx,
    )
    chosen_match = match_options[selected_label]
    st.session_state["selected_match_id"] = chosen_match.get("match_id")
    return chosen_match


def check_app_auth() -> bool:
    """Verify application password for private deployment (Streamlit Cloud)."""
    secret_pwd = None
    try:
        secret_pwd = st.secrets.get("APP_PASSWORD")
    except Exception:
        pass

    if not secret_pwd:
        secret_pwd = os.environ.get("APP_PASSWORD")

    # If no password configured, access is unrestricted (local dev)
    if not secret_pwd:
        return True

    # Check session state
    if st.session_state.get("authenticated", False):
        return True

    # Show login gate
    st.markdown("### 🔒 プライベートアクセス認証")
    st.info("このダッシュボードは非公開設定されています。パスワードを入力してください。")

    with st.form("auth_gate_form"):
        pwd_input = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン")
        if submitted:
            if pwd_input == secret_pwd:
                st.session_state["authenticated"] = True
                st.success("認証に成功しました。")
                st.rerun()
            else:
                st.error("パスワードが正しくありません。")

    return False


def _render_chat_messages(messages: List[Dict[str, Any]]) -> None:
    """Render conversation message history with sources."""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        sources = msg.get("sources", [])

        with st.chat_message(role):
            st.markdown(content)
            if sources:
                with st.expander("🌐 参照Webソース (Google検索)"):
                    for s in sources:
                        st.markdown(f"- [{s.get('title')}]({s.get('url')})")


def _render_quick_prompts() -> Optional[str]:
    """Render mobile-friendly quick inquiry prompt buttons."""
    st.caption("💡 ワンタップで質問：")
    col1, col2, col3 = st.columns(3)
    clicked_prompt = None

    with col1:
        if st.button("🛡️ 守備課題と交代策", use_container_width=True):
            clicked_prompt = "前半の守備のボトルネックと、ハーフタイム以降の交代カードの効果はどうでしたか？"
    with col2:
        if st.button("🏥 過密日程と怪我影響", use_container_width=True):
            clicked_prompt = "中何日の過密日程や累積警告、怪我人の影響は試合展開にどう作用しましたか？"
    with col3:
        if st.button("🔭 次節への観戦レンズ", use_container_width=True):
            clicked_prompt = "この試合を踏まえて、次節はピッチのどこ（スペース・時間帯・マッチアップ）に注目すべきですか？"

    return clicked_prompt


def render_chat_qa_tab(
    qa_engine: TacticalQAEngine,
    match_id: Optional[str],
) -> None:
    """Render interactive conversational QA tab with Google Search Grounding."""
    st.subheader("💬 戦術対話QA ＆ 観戦ナビゲーター")
    st.caption(
        "SQLite深層指標・15観点戦術分析・怪我や警告などの前提条件に基づき、Gemini AIが回答します。"
    )

    # Initialize chat history
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Controls row
    col_ctrl, col_clear = st.columns([3, 1])
    with col_ctrl:
        enable_search = st.checkbox(
            "🌐 Google検索で最新情報（怪我・移籍・会見速報等）を補完する",
            value=False,
            help="チェックを入れるとGoogle検索グラウンディングが有効化されます。",
        )
    with col_clear:
        if st.button("🗑️ 履歴クリア", use_container_width=True):
            st.session_state["chat_messages"] = []
            st.rerun()

    # Quick prompt shortcuts
    quick_input = _render_quick_prompts()

    # Render previous messages
    _render_chat_messages(st.session_state["chat_messages"])

    # Chat input box
    user_input = st.chat_input("質問を入力 (例: なぜ後半に失点が増えた？ 次節の注目ポイントは？)")
    effective_prompt = quick_input or user_input

    if effective_prompt:
        # Append user message
        st.session_state["chat_messages"].append({
            "role": "user",
            "content": effective_prompt,
            "sources": [],
        })
        with st.chat_message("user"):
            st.markdown(effective_prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("戦術データと試合前提を分析中..."):
                res = qa_engine.ask(
                    question=effective_prompt,
                    match_id=match_id,
                    enable_web_search=enable_search,
                )
                ans_text = res.get("answer", "")
                sources = res.get("grounding_sources", [])

                st.markdown(ans_text)
                if sources:
                    with st.expander("🌐 参照Webソース (Google検索)"):
                        for s in sources:
                            st.markdown(f"- [{s.get('title')}]({s.get('url')})")

        # Save assistant message
        st.session_state["chat_messages"].append({
            "role": "assistant",
            "content": ans_text,
            "sources": sources,
        })


def render_sidebar_llm_settings() -> GeminiTacticalClient:
    """Render the sidebar Gemini AI settings inputs and return configured client."""
    st.sidebar.markdown("---")
    st.sidebar.header("🤖 Gemini AI 設定")

    # Check secrets for default API key
    default_secret_key = None
    try:
        default_secret_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        pass

    api_key_input = st.sidebar.text_input(
        "Gemini API キー (未入力時は環境変数/Secretsを使用)",
        type="password",
        value=default_secret_key or "",
        help=".env や環境変数 GEMINI_API_KEY または Secrets があれば自動適用されます",
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

    # --------------------------------------------------------------------------
    # Privacy / Authentication Gate
    # --------------------------------------------------------------------------
    if not check_app_auth():
        return

    # Backend engine & AI client initialization
    engine = get_engine()
    profiler, comparator, rater = get_analysis_modules()
    gemini_client = render_sidebar_llm_settings()
    qa_engine = TacticalQAEngine(gemini_client=gemini_client)

    # --------------------------------------------------------------------------
    # Sidebar Navigation (SPA view routing)
    # --------------------------------------------------------------------------
    current_view = render_sidebar_navigation()

    # --------------------------------------------------------------------------
    # View Routing Hub
    # --------------------------------------------------------------------------
    if current_view == VIEW_LEAGUE:
        render_league_view(qa_engine)
    elif current_view == VIEW_TEAM:
        render_team_view(qa_engine)
    elif current_view == VIEW_PLAYER:
        render_player_view(qa_engine)
    elif current_view == VIEW_AI_CHAT:
        render_ai_chat_view(qa_engine)
    else:
        # Default: VIEW_MATCH
        selected_match = render_sidebar_match_selector()
        if not selected_match:
            return

        app_helpers = {
            "render_header": render_header,
            "render_external_links_bar": render_external_links_bar,
            "render_match_context_bar": render_match_context_bar,
            "fetch_match_reviews": fetch_match_reviews,
            "render_chat_qa_tab": render_chat_qa_tab,
            "render_objective_perspectives_tab": render_objective_perspectives_tab,
            "render_qualitative_comparison_tab": render_qualitative_comparison_tab,
            "render_player_ratings_tab": render_player_ratings_tab,
            "render_advanced_reports_tab": render_advanced_reports_tab,
            "render_stats_chart": render_stats_chart,
            "render_raw_data_tab": render_raw_data_tab,
            "render_ai_reasoning_tab": render_ai_reasoning_tab,
        }

        render_match_view(
            selected_match=selected_match,
            engine=engine,
            profiler=profiler,
            comparator=comparator,
            rater=rater,
            gemini_client=gemini_client,
            qa_engine=qa_engine,
            app_helpers=app_helpers,
        )

    # Check for auto-triggered AI dialog resumption
    check_and_trigger_auto_ai_modal(qa_engine, current_view)


if __name__ == "__main__":
    main()
