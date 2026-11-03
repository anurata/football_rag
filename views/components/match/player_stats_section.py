"""
views/components/match/player_stats_section.py

Section 5: All Player Stats Table
- Official face photos for all players
- Dynamic sorting by various metrics (CBP, shots, passes, distance, sprints, etc.)
- Deep link to Player Profile view
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st

from agent.objective_profiler import resolve_team_name
from agent.qa_engine import TacticalQAEngine
from pipeline.match_data_engine import fetch_match_players_with_details
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_MATCH, VIEW_PLAYER, navigate_to


def _sort_players(
    players: List[Dict[str, Any]],
    sort_key: str,
) -> List[Dict[str, Any]]:
    """Sort player dicts by the selected metric descending."""
    return sorted(players, key=lambda p: p.get(sort_key, 0) or 0, reverse=True)


def _render_player_stats_table(
    team_name: str,
    team_id: str,
    players: List[Dict[str, Any]],
    sort_key: str,
) -> None:
    """Render formatted player stats cards/table with face photos."""
    st.markdown(f"##### {team_name} ({team_id}) 選手スタッツ一覧")
    if not players:
        st.info("選手スタッツデータがありません。")
        return

    sorted_p = _sort_players(players, sort_key)

    for p in sorted_p:
        pname = p.get("player_name", "")
        p_id = p.get("player_id", "")
        num = p.get("number", 0)
        pos = p.get("position", "MF")
        mins = p.get("minutes", 0)
        photo_url = p.get("photo_url")
        cbp = p.get("cbp_total", 0.0)
        goals = p.get("goals", 0)
        assists = p.get("assists", 0)
        sprints = p.get("sprints", 0)
        dist = p.get("distance_km", 0.0)
        duels = p.get("duels_won", 0)

        img_html = ""
        if photo_url:
            img_html = f"""
            <div style="width: 44px; height: 44px; border-radius: 50%; overflow: hidden; background: #e2e8f0; border: 1px solid #475569; flex-shrink: 0;">
                <img src="{photo_url}" style="width: 100%; height: 100%; object-fit: cover;">
            </div>
            """
        else:
            img_html = """
            <div style="width: 44px; height: 44px; border-radius: 50%; background: #334155; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; color: #cbd5e1; flex-shrink: 0;">
                👤
            </div>
            """

        col_card, col_link = st.columns([4, 1])
        with col_card:
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; gap: 12px; background: #1e293b; padding: 8px 12px; border-radius: 6px; margin-bottom: 6px; border: 1px solid #334155;">
                    {img_html}
                    <div style="min-width: 130px;">
                        <span style="font-weight: bold; color: #60a5fa;">#{num}</span>
                        <strong style="color: #f8fafc; font-size: 0.95rem; margin-left: 4px;">{pname}</strong>
                        <div style="font-size: 0.78rem; color: #94a3b8;">{pos} ｜ {mins}分</div>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-left: auto; font-size: 0.82rem; color: #cbd5e1;">
                        <span>CBP: <b style="color: #38bdf8;">{cbp}</b></span>
                        <span>得点: <b style="color: #4ade80;">{goals}</b></span>
                        <span>アシスト: <b style="color: #a78bfa;">{assists}</b></span>
                        <span>スプリント: <b>{sprints}</b></span>
                        <span>走行: <b>{dist}km</b></span>
                        <span>デュエル勝: <b>{duels}</b></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_link:
            if st.button("詳細 ❯", key=f"btn_p_det_{team_id}_{num}_{pname}"):
                navigate_to(
                    view=VIEW_PLAYER,
                    team_id=team_id,
                    player_id=p_id,
                    player_name=pname,
                )


def render_match_player_stats_section(
    match_id: str,
    home_id: str,
    away_id: str,
    qa_engine: TacticalQAEngine,
) -> None:
    """Render full Section 5: All Player Stats Table with photos & sorting."""
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.subheader("⑤ 全選手スタッツ一覧 ＆ 公式顔写真")
        st.caption("※出場全選手の顔写真、CBP内訳、走力・デュエルスタッツ（指定指標順で動的ソート可能）")
    with col_btn:
        render_ai_button(
            button_key=f"ai_btn_sec5_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="player_stats_table",
            note="全選手スタッツ・CBPマトリクスについて質問",
            button_label="🤖 スタッツをAI質問",
        )

    home_players = fetch_match_players_with_details(match_id=match_id, team_id=home_id)
    away_players = fetch_match_players_with_details(match_id=match_id, team_id=away_id)

    col_sort, col_team_filter = st.columns([2, 1])
    with col_sort:
        sort_options = {
            "cbp_total": "CBP総合ポイント順",
            "goals": "得点数順",
            "assists": "アシスト数順",
            "sprints": "スプリント回数順",
            "distance_km": "走行距離順",
            "duels_won": "デュエル勝利数順",
            "touches": "ボールタッチ数順",
        }
        selected_sort = st.selectbox(
            "並び替え指標",
            options=list(sort_options.keys()),
            format_func=lambda k: sort_options[k],
            key=f"player_stats_sort_{match_id}",
        )
    with col_team_filter:
        team_options = ["両チーム", f"🔵 {resolve_team_name(home_id)}", f"🔴 {resolve_team_name(away_id)}"]
        selected_filter = st.radio(
            "表示対象チーム",
            options=team_options,
            horizontal=True,
            key=f"player_stats_team_filter_{match_id}",
        )

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    if selected_filter in ["両チーム", f"🔵 {resolve_team_name(home_id)}"]:
        _render_player_stats_table(
            team_name=f"🔵 {resolve_team_name(home_id)}",
            team_id=home_id,
            players=home_players,
            sort_key=selected_sort,
        )

    if selected_filter in ["両チーム", f"🔴 {resolve_team_name(away_id)}"]:
        _render_player_stats_table(
            team_name=f"🔴 {resolve_team_name(away_id)}",
            team_id=away_id,
            players=away_players,
            sort_key=selected_sort,
        )
