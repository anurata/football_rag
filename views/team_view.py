"""
views/team_view.py

2. Team Profile & Analytics page.
Club tactical profiles, 55 tactical metrics, roster CBP rankings, and club comparisons.
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from agent.objective_profiler import resolve_team_name, TEAM_NAME_MAP
from agent.qa_engine import TacticalQAEngine
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_PLAYER, VIEW_TEAM, navigate_to


def render_team_view(qa_engine: TacticalQAEngine) -> None:
    """Render Team Profile & Analytics view."""
    st.title("🛡️ チーム毎の戦術観戦ガイド (Team Profile)")
    st.markdown(
        "クラブの戦術プロファイル（55戦術指標）、直近調子（Form）、"
        "所属選手のCBP（チャンスビルディングポイント）順位、および他クラブとの直接対比を提供します。"
    )

    # Team selector
    team_keys = list(TEAM_NAME_MAP.keys())
    current_team = st.session_state.get("selected_team_id")
    default_idx = team_keys.index(current_team) if current_team in team_keys else 0

    selected_team = st.selectbox(
        "分析対象クラブを選択",
        options=team_keys,
        index=default_idx,
        format_func=lambda tid: f"{resolve_team_name(tid)} ({tid})",
        key="team_view_selector",
    )
    st.session_state["selected_team_id"] = selected_team

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        render_ai_button(
            button_key=f"team_ai_btn_{selected_team}",
            view_type=VIEW_TEAM,
            qa_engine=qa_engine,
            team_id=selected_team,
            section_key="tactics",
            note=f"{resolve_team_name(selected_team)}の戦術スタイルや強みについて質問",
            button_label="🤖 このクラブについてAIに質問",
        )

    st.divider()

    st.subheader(f"🛡️ {resolve_team_name(selected_team)} 戦術プロファイル (55指標)")
    st.caption("ポゼッション、プレッシング、カウンター、被決定機阻止などクラブ固有のスタイルを可視化します。")

    st.divider()

    st.subheader("👤 所属選手一覧 ＆ チャンスビルディングポイント (CBP)")
    st.caption("選手を選択すると、選手個人の詳細プロファイル（節別推移・採点履歴）へジャンプします。")

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        with st.container(border=True):
            st.markdown("##### 仲川 輝人 (FW #39)")
            st.caption("CBP: ドリブル部門上位 | 出場時間: 840分")
            if st.button("👤 仲川選手の詳細を見る", key="btn_nakagawa"):
                navigate_to(view=VIEW_PLAYER, team_id=selected_team, player_id="P_NAKAGAWA", player_name="仲川 輝人")
    with col_p2:
        with st.container(border=True):
            st.markdown("##### 小泉 慶 (MF #37)")
            st.caption("CBP: 奪取部門上位 | 出場時間: 900分")
            if st.button("👤 小泉選手の詳細を見る", key="btn_koizumi"):
                navigate_to(view=VIEW_PLAYER, team_id=selected_team, player_id="P_KOIZUMI", player_name="小泉 慶")
    with col_p3:
        with st.container(border=True):
            st.markdown("##### エンリケ トレヴィザン (DF #44)")
            st.caption("CBP: 守備・クリア部門上位 | 出場時間: 780分")
            if st.button("👤 トレヴィザン選手の詳細を見る", key="btn_trevisan"):
                navigate_to(view=VIEW_PLAYER, team_id=selected_team, player_id="P_TREVISAN", player_name="エンリケ トレヴィザン")

