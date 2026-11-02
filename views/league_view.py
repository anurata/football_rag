"""
views/league_view.py

1. J-League League Overview page (standings, expected points, matchweek cards).
Provides deep-linking to team and match views and ubiquitous AI QA integration.
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from agent.qa_engine import TacticalQAEngine
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_LEAGUE, VIEW_MATCH, VIEW_TEAM, navigate_to


def render_league_view(qa_engine: TacticalQAEngine) -> None:
    """Render J-League Overview view."""
    st.title("🏆 Jリーグ全体 観戦ガイド (League Overview)")
    st.markdown(
        "最新の順位表・期待値（xPTS / xG / xGA）、節別日程・試合結果カード、"
        "リーグスタッツランキング、および戦術ポジショニング比較を提供します。"
    )

    col_btn, _ = st.columns([1, 4])
    with col_btn:
        render_ai_button(
            button_key="league_header_ai_btn",
            view_type=VIEW_LEAGUE,
            qa_engine=qa_engine,
            section_key="overview",
            note="Jリーグ全体の順位・戦術トレンドについて質問",
            button_label="🤖 リーグ全体についてAIに質問",
        )

    st.divider()

    st.subheader("📊 最新順位表 ＆ 期待値 (xPTS / xG / xGA)")
    st.caption("チーム名をクリックすると、クラブごとの詳細ページ（55指標・所属選手）へ遷移します。")

    # Sample deep-link buttons to demonstrate SPA transitions
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        if st.button("🛡️ FC東京の分析を見る", key="btn_fct_from_league"):
            navigate_to(view=VIEW_TEAM, team_id="FCT")
    with col_t2:
        if st.button("🛡️ FC町田ゼルビアの分析を見る", key="btn_zel_from_league"):
            navigate_to(view=VIEW_TEAM, team_id="ZEL")
    with col_t3:
        if st.button("🛡️ 鹿島アントラーズの分析を見る", key="btn_kas_from_league"):
            navigate_to(view=VIEW_TEAM, team_id="KAS")

    st.divider()

    st.subheader("⚽ 節別日程 ＆ 試合結果カード")
    st.caption("試合カードを選択すると、該当試合の深層分析ページへ直接ジャンプします。")

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        with st.container(border=True):
            st.markdown("##### 2026 第1節: FC東京 vs FC町田ゼルビア")
            st.caption("🏟️ 味の素スタジアム | 公式戦")
            if st.button("⚽ 試合詳細・5大セクションを見る", key="btn_m1_from_league"):
                navigate_to(view=VIEW_MATCH, match_id="2026102505")
    with col_m2:
        with st.container(border=True):
            st.markdown("##### 2026 第13節: ファジアーノ岡山 vs FC東京")
            st.caption("🏟️ シティライトスタジアム | 公式戦")
            if st.button("⚽ 試合詳細・5大セクションを見る", key="btn_m2_from_league"):
                navigate_to(view=VIEW_MATCH, match_id="20261031_OKA_FCT")

