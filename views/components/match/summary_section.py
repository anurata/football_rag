"""
views/components/match/summary_section.py

Section 1: Match Summary & Narrative Flow
- High-level narrative summary
- Starting & in-game tactical formations
- Sequential match event timeline
- Press conference interviews and media discourse summary
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from agent.objective_profiler import resolve_team_name
from agent.qa_engine import TacticalQAEngine
from pipeline.match_data_engine import (
    fetch_match_formations,
    fetch_match_interviews_and_reviews,
    fetch_match_timeline_events,
)
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_MATCH


def _render_narrative_card(struct_summary: Dict[str, Any]) -> None:
    """Render high-level structural match summary and narrative text."""
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


def _render_formation_board(
    match_id: str,
    home_id: str,
    away_id: str,
) -> None:
    """Render formation overview and in-game tactical adjustments."""
    fm = fetch_match_formations(match_id)
    home_name = resolve_team_name(home_id)
    away_name = resolve_team_name(away_id)

    st.markdown("##### 📐 フォーメーション ＆ 布陣変化")

    col_h, col_a = st.columns(2)
    with col_h:
        st.markdown(
            f"""
            <div style="background: #1e293b; border-radius: 8px; padding: 14px; border-left: 4px solid #3b82f6;">
                <strong style="color: #60a5fa; font-size: 1.0rem;">🔵 {home_name} ({home_id})</strong>
                <div style="font-size: 1.25rem; font-weight: bold; margin: 6px 0; color: #f8fafc;">
                    基本布陣: <code>{fm.get('home_initial', '4-2-3-1')}</code>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        changes = fm.get("home_changes", [])
        if len(changes) > 1:
            st.caption(f"🔄 試合中の布陣変化: {' ➔ '.join(changes)}")

    with col_a:
        st.markdown(
            f"""
            <div style="background: #1e293b; border-radius: 8px; padding: 14px; border-left: 4px solid #f43f5e;">
                <strong style="color: #f43f5e; font-size: 1.0rem;">🔴 {away_name} ({away_id})</strong>
                <div style="font-size: 1.25rem; font-weight: bold; margin: 6px 0; color: #f8fafc;">
                    基本布陣: <code>{fm.get('away_initial', '4-2-3-1')}</code>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        changes = fm.get("away_changes", [])
        if len(changes) > 1:
            st.caption(f"🔄 試合中の布陣変化: {' ➔ '.join(changes)}")


def _render_timeline(match_id: str) -> None:
    """Render match events timeline (goals, subs, cards)."""
    events = fetch_match_timeline_events(match_id)
    st.markdown("##### ⏱️ 試合の流れ ＆ キーイベント・タイムライン")

    if not events:
        st.info("タイムラインイベントデータがありません。")
        return

    for ev in events:
        m = ev.get("minute", 0)
        etype = ev.get("event_type", "EVENT")
        pname = ev.get("player_name", "")
        desc = ev.get("description", "")
        tid = ev.get("team_id", "")

        icon = "⚽" if "GOAL" in etype else "🔄" if "SUB" in etype else "🟨" if "CARD" in etype else "⚡"
        border_c = "#10b981" if "GOAL" in etype else "#3b82f6" if "SUB" in etype else "#f59e0b"

        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px; padding: 8px 12px; background: #0f172a; border-radius: 6px; border-left: 3px solid {border_c};">
                <span style="font-weight: bold; color: #94a3b8; min-width: 38px;">{m}'</span>
                <span style="font-size: 1.1rem;">{icon}</span>
                <span style="font-weight: 600; color: #f8fafc;">{pname} <small style="color: #94a3b8;">({tid})</small></span>
                <span style="color: #cbd5e1; font-size: 0.88rem; margin-left: auto;">{desc}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_interviews_and_discourse(match_id: str) -> None:
    """Render post-match press conferences and discourse summaries."""
    reviews_dict = fetch_match_interviews_and_reviews(match_id)
    officials = reviews_dict.get("official", [])
    interviews = reviews_dict.get("home_interviews", [])
    discourse = reviews_dict.get("discourse", [])

    st.markdown("##### 🎙️ 選手・監督インタビュー要約 ＆ 主要言説まとめ")

    with st.expander("📝 公式レポート・戦評全文", expanded=False):
        if not officials:
            st.caption("公式レポートの登録がありません。")
        for item in officials:
            st.markdown(f"**{item.get('title', '公式戦評')}**")
            st.markdown(item.get("content", ""))

    with st.expander("🗣️ 監督・選手インタビュー", expanded=False):
        if not interviews:
            st.caption("インタビューコメントの登録がありません。")
        for item in interviews:
            spk = item.get("speaker", "選手")
            st.markdown(f"**【{spk}】{item.get('title', '')}**")
            st.markdown(f"> *「{item.get('content', '')}」*")

    if discourse:
        with st.expander("🌐 レビューサイト・主要チャンネル言説まとめ", expanded=False):
            for item in discourse:
                st.markdown(f"**{item.get('title', '言説要約')}**")
                st.markdown(item.get("content", ""))


def render_match_summary_section(
    match_id: str,
    home_id: str,
    away_id: str,
    struct_summary: Optional[Dict[str, Any]],
    qa_engine: TacticalQAEngine,
) -> None:
    """Render full Section 1: Match Summary."""
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.subheader("① 試合サマリー ＆ 戦況ダイナミクス")
    with col_btn:
        render_ai_button(
            button_key=f"ai_btn_sec1_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="match_summary",
            note=f"試合サマリー・戦況の流れ（{home_id} vs {away_id}）について質問",
            button_label="🤖 サマリーをAI分析",
        )

    if struct_summary:
        _render_narrative_card(struct_summary)

    _render_formation_board(match_id=match_id, home_id=home_id, away_id=away_id)
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)
    _render_timeline(match_id=match_id)
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)
    _render_interviews_and_discourse(match_id=match_id)
    st.divider()
