"""
views/player_view.py

4. Player Profile & Analytics page.
Player basic stats, CBP positional radar, MW progression charts, and match rating timelines.
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from agent.objective_profiler import resolve_team_name, TEAM_NAME_MAP
from agent.qa_engine import TacticalQAEngine
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_MATCH, VIEW_PLAYER, navigate_to


def render_player_view(qa_engine: TacticalQAEngine) -> None:
    """Render Player Profile & Analytics view."""
    st.title("👤 選手名鑑 ＆ 個別スタッツ観戦ガイド (Player Profile)")
    st.markdown(
        "チーム絞り込み・選手検索、CBP（チャンスビルディングポイント）同ポジション平均比較レーダー、"
        "節別スタッツ推移、および出場試合別の採点・寸評タイムラインを提供します。"
    )

    current_player_name = st.session_state.get("selected_player_name") or "仲川 輝人"
    current_team_id = st.session_state.get("selected_team_id") or "FCT"

    col_sel_team, col_sel_name = st.columns([1, 2])
    with col_sel_team:
        team_keys = list(TEAM_NAME_MAP.keys())
        default_idx = team_keys.index(current_team_id) if current_team_id in team_keys else 0
        selected_team = st.selectbox(
            "所属チーム",
            options=team_keys,
            index=default_idx,
            format_func=lambda tid: resolve_team_name(tid),
            key="player_view_team_select",
        )
    with col_sel_name:
        player_name = st.text_input(
            "選手名で検索",
            value=current_player_name,
            key="player_view_name_search",
        )
    st.session_state["selected_team_id"] = selected_team
    st.session_state["selected_player_name"] = player_name

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        render_ai_button(
            button_key=f"player_ai_btn_{player_name}",
            view_type=VIEW_PLAYER,
            qa_engine=qa_engine,
            team_id=selected_team,
            player_name=player_name,
            section_key="player_overview",
            note=f"{player_name}選手のプレー特徴や今季の戦術的役割について質問",
            button_label="🤖 この選手についてAIに質問",
        )

    st.divider()

    st.subheader(f"👤 {player_name} ({resolve_team_name(selected_team)}) 基本情報 ＆ CBP特性")
    st.caption("同一ポジション平均（シュート・パス・ドリブル・クロス・奪取・守備）との対比を表示します。")

    st.divider()

    st.subheader("📅 出場試合履歴 ＆ 試合別採点・寸評タイムライン")
    st.caption("試合名をクリックすると、該当試合の詳細分析（5大セクション）へジャンプします。")

    with st.container(border=True):
        col_m_info, col_m_rate = st.columns([3, 1])
        with col_m_info:
            st.markdown("##### 2026 第1節: FC東京 vs FC町田ゼルビア")
            st.caption("先発出場 (後半72分交代) | ドリブル成功率 75% | 決定機演出 2回")
            if st.button("⚽ この試合の詳細分析へジャンプ", key="btn_jump_from_player_to_m1"):
                navigate_to(view=VIEW_MATCH, match_id="2026102505")
        with col_m_rate:
            st.markdown(
                "<div style='text-align:center;padding:8px;background:#f0fdf4;border-radius:8px;'>"
                "<div style='font-size:24px;font-weight:bold;color:#16a34a;'>6.5</div>"
                "<div style='font-size:11px;color:#15803d;'>採点 (10点満点)</div>"
                "</div>",
                unsafe_allow_html=True,
            )

