"""views/team_view.py

2. チーム毎の戦術観戦ガイド (Team Profile & Analytics)
機能:
- クラブ戦術プロファイル（動的クラスタ分析・新戦術スタイルラベリング）
- シグネチャー指標（他クラブと際立って異なる強み Top 3 & 割り切り/課題 Bottom 3）
- 5大戦術柱レーダーチャート（Plotly）
- 勝利時 vs 敗戦時スタッツ比較（勝ち筋・負け筋の定量的解剖）
- 「自分たちのサッカーができた」戦術スタイル合致試合（会心の試合 Top 3 & 試合詳細ジャンプ）
- 得点パターン & 15分時間帯別ダイナミクス
- スタメンユニット相性 & 相手戦術タイプ別耐性
- 全55戦術指標 6大カテゴリ別折りたたみ詳細テーブル
- 所属選手一覧 & CBPランキング（ポジション絞込・指標ソート・選手詳細ジャンプ）
- 他クラブ直接対比（Head-to-Head: レーダー重ね合わせ・主要10指標対比・直接対決実績）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from agent.objective_profiler import resolve_team_name
from agent.qa_engine import TacticalQAEngine
from pipeline.league_overview_data import get_league_standings
from pipeline.team_analytics_engine import (
    TEAM_ID_MAP,
    compute_all_teams_clusters,
    get_goal_pattern_breakdown,
    get_style_adherence_matches,
    get_team_55_metrics_categorized,
    get_team_emblem_html,
    get_team_h2h_comparison,
    get_team_manager_avatar_html,
    get_team_manager_info,
    get_team_signature_metrics,
    get_team_squad_cbp,
    get_win_loss_pattern_analysis,
    load_team_season_synthesis,
    load_team_tactical_profile_meta,
)
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_MATCH, VIEW_PLAYER, VIEW_TEAM, navigate_to


# ===========================================================================
# 1. メインエントリー
# ===========================================================================
def render_team_view(qa_engine: TacticalQAEngine) -> None:
    """Render Team Profile & Analytics view."""
    # クラブセレクター
    selected_team = _render_team_selector()

    # クラブメタ情報・クラスタ情報
    clusters_data = compute_all_teams_clusters()
    team_profiles = clusters_data.get("team_profiles", {})
    t_prof = team_profiles.get(selected_team, {})
    meta = load_team_tactical_profile_meta(selected_team)

    # ヘッダーサマリー表示
    _render_club_header(
        team_id=selected_team,
        t_prof=t_prof,
        meta=meta,
        qa_engine=qa_engine,
    )

    st.markdown("---")

    # 3タブ構成
    tab_tactics, tab_squad, tab_h2h = st.tabs([
        "📊 戦術プロファイル & スタイル",
        "👤 所属選手 & CBPリーダー",
        "⚔️ 他クラブ直接対比 (Head-to-Head)",
    ])

    with tab_tactics:
        _render_tactical_profile_tab(
            team_id=selected_team,
            t_prof=t_prof,
            qa_engine=qa_engine,
        )

    with tab_squad:
        _render_squad_tab(
            team_id=selected_team,
        )

    with tab_h2h:
        _render_h2h_tab(
            team_id=selected_team,
        )


# ===========================================================================
# 2. セレクター & クラブヘッダー
# ===========================================================================
def _get_sorted_team_list() -> List[Dict[str, Any]]:
    """順位表に基づき1位〜20位の順にチーム情報を取得する."""
    standings = get_league_standings()
    if standings:
        teams = []
        seen = set()
        for s in standings:
            tid = s.get("team_id")
            if tid in TEAM_ID_MAP and tid not in seen:
                seen.add(tid)
                teams.append({
                    "team_id": tid,
                    "team_name": resolve_team_name(tid),
                    "rank": s.get("rank", 99),
                    "points": s.get("points", 0),
                })
        # 順位順にソート
        teams.sort(key=lambda x: x["rank"])
        if teams:
            return teams

    # フォールバック (順位表がない場合)
    return [
        {
            "team_id": tid,
            "team_name": resolve_team_name(tid),
            "rank": i + 1,
            "points": 0,
        }
        for i, tid in enumerate(TEAM_ID_MAP.keys())
    ]


def _render_team_dialog_body(
    sorted_teams: List[Dict[str, Any]],
    current_team: str,
) -> None:
    """モバイル用クラブ選択モーダルダイアログの本文を描画する."""
    st.markdown("### 🛡️ J1分析対象クラブを選択")
    st.caption("現在の順位順に並んでいます。クラブをタップすると即座に切り替わります。")
    st.write("")

    # 2カラムグリッドでクラブカードを一覧表示
    for i in range(0, len(sorted_teams), 2):
        pair = sorted_teams[i : i + 2]
        cols = st.columns(2)
        for col, t_info in zip(cols, pair):
            tid = t_info["team_id"]
            is_active = (tid == current_team)
            with col:
                with st.container(border=True):
                    # エンブレムとクラブ名
                    emblem_html = get_team_emblem_html(tid, width=38, height=38)
                    active_border = "border-left: 3px solid #2563eb;" if is_active else ""
                    st.markdown(
                        f"<div style='display: flex; align-items: center; gap: 8px; {active_border} padding-left: 4px;'>"
                        f"  {emblem_html}"
                        f"  <div>"
                        f"    <div style='font-size: 11px; color: #64748b; font-weight: 700;'>第{t_info['rank']}位 ｜ {t_info['points']}pts</div>"
                        f"    <div style='font-size: 13.5px; font-weight: 700; color: #1e293b;'>{t_info['team_name']}</div>"
                        f"  </div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    st.write("")
                    if is_active:
                        st.button(
                            "選択中",
                            key=f"btn_modal_sel_{tid}",
                            disabled=True,
                            use_container_width=True,
                        )
                    else:
                        if st.button(
                            "分析を見る",
                            key=f"btn_modal_sel_{tid}",
                            use_container_width=True,
                        ):
                            st.session_state["selected_team_id"] = tid
                            st.rerun()


@st.dialog("🛡️ クラブ選択", width="large")
def _show_team_select_dialog(
    sorted_teams: List[Dict[str, Any]],
    current_team: str,
) -> None:
    """モバイル用クラブ選択ダイアログを開く."""
    _render_team_dialog_body(sorted_teams, current_team)


def _inject_sticky_team_selector_css() -> None:
    """スクロール追従・上部固定（Sticky）およびPC/モバイル切り替えCSSを注入する."""
    st.markdown(
        """
        <style>
        /* 祖先ラッパーのoverflow制約を解除してStickyを確実に有効化 */
        div[data-testid="stLayoutWrapper"]:has(.sticky-team-badge),
        div[data-testid="stVerticalBlock"]:has(.sticky-team-badge) {
            overflow: visible !important;
        }

        /* チーム名バーの上部固定表示 (Sticky Header) */
        div[data-testid="stLayoutWrapper"]:has(.sticky-team-badge) {
            position: sticky !important;
            top: 56px !important;
            z-index: 999 !important;
            background: rgba(255, 255, 255, 0.97) !important;
            backdrop-filter: blur(10px) !important;
            -webkit-backdrop-filter: blur(10px) !important;
            padding: 4px 8px !important;
            border-radius: 8px !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
            margin-bottom: 8px !important;
        }

        div[data-testid="stHorizontalBlock"]:has(.sticky-team-badge) {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            align-items: center !important;
            padding: 0 !important;
            margin: 0 !important;
        }

        .sticky-team-badge {
            display: flex !important;
            align-items: center !important;
            gap: 8px !important;
        }

        /* PC用横一列エンブレムストリップ */
        .pc-team-strip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            overflow-x: auto;
            gap: 6px;
            padding: 6px 4px 8px 4px;
            margin-bottom: 14px;
            border-bottom: 1px solid #f1f5f9;
            scrollbar-width: thin;
        }
        .pc-team-strip::-webkit-scrollbar {
            height: 4px;
        }
        .pc-team-strip::-webkit-scrollbar-thumb {
            background-color: #cbd5e1;
            border-radius: 4px;
        }

        .team-strip-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            padding: 4px 6px;
            border-radius: 6px;
            border: 1.5px solid transparent;
            transition: all 0.15s ease-in-out;
            min-width: 44px;
            box-sizing: border-box;
        }
        .team-strip-item:hover {
            background-color: #f8fafc;
            transform: translateY(-1px);
        }
        .team-strip-item.active {
            border-color: #2563eb;
            background-color: #eff6ff;
            box-shadow: 0 1px 3px rgba(37, 99, 235, 0.12);
        }
        .team-strip-item .rank-tag {
            font-size: 10px;
            font-weight: 700;
            color: #475569;
            margin-top: 2px;
            white-space: nowrap;
        }
        .team-strip-item.active .rank-tag {
            color: #2563eb;
            font-weight: 800;
        }

        /* モバイル画面 (幅 <= 768px): PC用ストリップを完全非表示 */
        @media (max-width: 768px) {
            .pc-team-strip-container {
                display: none !important;
            }
        }
        /* PC画面 (幅 > 768px): PC用ストリップを表示 */
        @media (min-width: 769px) {
            .pc-team-strip-container {
                display: block !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_team_selector() -> str:
    """
    分析対象クラブ選択バー (レスポンシブ・上部固定).
    PC画面: 上部に固定チーム名バー + 順位順に横一列にエンブレムを並べて選択.
    モバイル画面: 上部に固定チーム名バー ＋ クラブ選択ダイアログ.
    """
    _inject_sticky_team_selector_css()
    sorted_teams = _get_sorted_team_list()

    valid_ids = [t["team_id"] for t in sorted_teams]

    # クエリパラメータによる選択切り替えを検知
    qp_team = st.query_params.get("team")
    if qp_team and qp_team in valid_ids:
        st.session_state["selected_team_id"] = qp_team

    current_team = st.session_state.get("selected_team_id")
    if current_team not in valid_ids:
        current_team = valid_ids[0] if valid_ids else "FCT"
        st.session_state["selected_team_id"] = current_team

    cur_info = next((t for t in sorted_teams if t["team_id"] == current_team), sorted_teams[0])

    # --------------------------------------------------------------------------
    # 1. スクロールしても上部に固定表示される「チーム名バー」 (Sticky Header)
    # --------------------------------------------------------------------------
    col_team_info, col_team_btn = st.columns([3.4, 1.6], vertical_alignment="center")
    with col_team_info:
        emblem_img = get_team_emblem_html(current_team, width=34, height=34)
        st.markdown(
            f"<div class='sticky-team-badge'>"
            f"  {emblem_img}"
            f"  <div>"
            f"    <span style='font-size: 15px; font-weight: 800; color: #0f172a;'>{cur_info['team_name']}</span>"
            f"    <span style='font-size: 11.5px; font-weight: 700; color: #2563eb; background: #eff6ff; padding: 2px 7px; border-radius: 4px; margin-left: 6px; border: 1px solid #bfdbfe; white-space: nowrap;'>第{cur_info['rank']}位 ({cur_info['points']}pts)</span>"
            f"  </div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_team_btn:
        if st.button("クラブ変更 ▾", key="btn_sticky_change_team", use_container_width=True):
            _show_team_select_dialog(sorted_teams, current_team)

    # --------------------------------------------------------------------------
    # 2. PC用横一列エンブレムバー (幅 > 768px で表示、順位順20クラブ)
    # --------------------------------------------------------------------------
    strip_items_html = []
    for t_info in sorted_teams:
        tid = t_info["team_id"]
        is_active = (tid == current_team)
        active_cls = "active" if is_active else ""
        emblem_svg = get_team_emblem_html(tid, width=28, height=28)
        item_html = (
            f"<a href='?team={tid}' target='_self' class='team-strip-item {active_cls}' title='第{t_info['rank']}位 {t_info['team_name']} ({t_info['points']}pts)'>"
            f"  {emblem_svg}"
            f"  <span class='rank-tag'>{t_info['rank']}位</span>"
            f"</a>"
        )
        strip_items_html.append(item_html)

    full_pc_strip_html = (
        f"<div class='pc-team-strip-container'>"
        f"  <div style='font-size: 11.5px; color: #64748b; margin-bottom: 4px;'>"
        f"    🏆 <b>J1全20クラブ (順位順)</b> ｜ エンブレムをクリックして分析対象を即座に切り替え"
        f"  </div>"
        f"  <div class='pc-team-strip'>"
        f"    {''.join(strip_items_html)}"
        f"  </div>"
        f"</div>"
    )
    st.markdown(full_pc_strip_html, unsafe_allow_html=True)

    return current_team


def _render_club_header(
    team_id: str,
    t_prof: Dict[str, Any],
    meta: Dict[str, Any],
    qa_engine: TacticalQAEngine,
) -> None:
    """クラブ基本情報、新戦術スタイルバッジ、Form、AIボタンを表示."""
    team_name = resolve_team_name(team_id)
    manager = meta.get("manager", "監督情報準備中")
    base_f = meta.get("base_formation", "4-2-3-1")
    style_label = t_prof.get("style_label", "バランス型")

    # 順位表から今季スタッツを取得
    standings = get_league_standings()
    s_info = next((s for s in standings if s.get("team_id") == team_id), None)
    rank_val = s_info.get("rank") if s_info else None
    pts_val = s_info.get("points") if s_info else None
    rank_str = f"J1 第{rank_val}位" if rank_val is not None else "J1"
    pts_str = f"{pts_val} pts" if pts_val is not None else "-"
    form_badges = s_info.get("form", []) if s_info else []

    col_logo, col_info, col_right = st.columns([1, 4, 3])

    with col_logo:
        st.markdown(
            f"<div style='text-align: center; padding-top: 6px;'>"
            f"{get_team_emblem_html(team_id, width=82, height=82)}"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col_info:
        mgr_avatar = get_team_manager_avatar_html(team_id, size=46)
        st.markdown(f"## {team_name} <span style='font-size: 1.2rem; color: #757575;'>({team_id})</span>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='display: flex; align-items: center; gap: 12px; margin-bottom: 6px;'>"
            f"  {mgr_avatar}"
            f"  <div>"
            f"    <div style='font-size: 0.95rem; line-height: 1.3;'><b>{rank_str}</b> ({pts_str}) ｜ 基本布陣: <code>{base_f}</code></div>"
            f"    <div style='color: #334155; font-size: 0.9rem; line-height: 1.3;'>指揮官: <b>{manager} 監督</b></div>"
            f"  </div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"🏷️ **動的戦術分類**: :blue-background[**{style_label}**]"
        )

    with col_right:
        # 直近戦績 (Form)
        st.markdown("**直近5試合の戦績 (Form)**")
        form_cols = st.columns(5)
        badge_map = {"W": "🟢 勝", "D": "⚪ 分", "L": "🔴 負"}
        for idx, res in enumerate(form_badges[:5]):
            with form_cols[idx]:
                st.caption(badge_map.get(res, res))

        st.write("")
        render_ai_button(
            button_key=f"team_header_ai_{team_id}",
            view_type=VIEW_TEAM,
            qa_engine=qa_engine,
            team_id=team_id,
            section_key="tactical_style",
            note=f"{team_name}の戦術スタイルや強みについて質問",
            button_label="🤖 このクラブをAI分析",
        )


# ===========================================================================
# 3. タブ1: 戦術プロファイル & スタイル
# ===========================================================================
def _render_tactical_profile_tab(
    team_id: str,
    t_prof: Dict[str, Any],
    qa_engine: TacticalQAEngine,
) -> None:
    """戦術プロファイルタブ全体の描画."""
    _inject_metric_table_custom_css()
    st.subheader("1. クラブ戦術スタイル ＆ 際立つ特徴指標")

    style_desc = t_prof.get("style_description", "")
    cluster_mates = t_prof.get("cluster_mates", [])
    mate_names = [resolve_team_name(tid) for tid in cluster_mates[:4]]

    st.info(
        f"**【戦術DNA】**: {style_desc}\n\n"
        f"*(同系統スタイルの他クラブ: {', '.join(mate_names) if mate_names else 'なし'})*"
    )

    # シグネチャー指標（強み Top 3 & 課題 Bottom 3）
    _render_signature_metrics_section(team_id)

    st.write("")
    st.subheader("2. 5大戦術柱 レーダーチャート")
    st.caption("ポゼッション、前進推進、ハイプレス強度、フィジカル走力、ゴール期待度の0〜100正規化スコアです。")
    _render_tactical_radar_chart(t_prof)

    st.markdown("---")
    st.subheader("3. 勝敗パターン分析（勝ち筋・負け筋の解剖）")
    st.caption("今季の「勝利試合」と「敗戦試合」でのスタッツギャップを抽出し、どのような条件だと勝ちやすく、どう攻められると脆いかを分析します。")
    _render_win_loss_analysis_section(team_id)

    st.markdown("---")
    st.subheader("4. 🏆 「自分たちのサッカーができた」会心の試合 Top 3")
    st.caption("単なるスコアだけでなく、チーム固有の戦術スタイル（理想の指標水準）を高度に体現できた試合を抽出しています。")
    _render_style_adherence_section(team_id)

    st.markdown("---")
    st.subheader("5. 得点パターン & 15分時間帯別ダイナミクス")
    _render_goal_and_time_dynamics_section(team_id)

    st.markdown("---")
    st.subheader("6. スタメンユニット相性 & 相手戦術タイプ別耐性")
    _render_cross_analytics_section(team_id)

    st.markdown("---")
    st.subheader("7. 全55戦術指標 完全データ (6大カテゴリ)")
    st.caption("各指標をクリックして開くと、シーズン平均値、直近節値、リーグ平均との比較が確認できます。")
    _render_55_metrics_expander_section(team_id)


def _render_signature_metrics_section(team_id: str) -> None:
    """突出した武器 Top 3 と 顕著な割り切り/課題 Bottom 3 を表示."""
    sig_data = get_team_signature_metrics(team_id)
    top_strengths = sig_data.get("top_strengths", [])
    bottom_weaknesses = sig_data.get("bottom_weaknesses", [])

    col_str, col_weak = st.columns(2)

    with col_str:
        st.markdown("##### 🌟 際立つ最大の武器 (Top 3 強み)")
        for item in top_strengths:
            with st.container(border=True):
                st.markdown(f"**{item['metric_name']}**")
                c1, c2, c3 = st.columns(3)
                c1.metric("チーム平均", f"{item['team_value']}")
                c2.metric("リーグ平均", f"{item['league_average']}")
                c3.metric("リーグ順位", f"{item['rank']}位 / {item['total_teams']}")
                st.caption(f"偏差乖離: **{item['z_score']:+.2f} σ**（リーグ上位の突出したストロングポイント）")

    with col_weak:
        st.markdown("##### ⚠️ 顕著な割り切り・改善課題 (Bottom 3 特徴)")
        for item in bottom_weaknesses:
            with st.container(border=True):
                st.markdown(f"**{item['metric_name']}**")
                c1, c2, c3 = st.columns(3)
                c1.metric("チーム平均", f"{item['team_value']}")
                c2.metric("リーグ平均", f"{item['league_average']}")
                c3.metric("リーグ順位", f"{item['rank']}位 / {item['total_teams']}")
                st.caption(f"偏差乖離: **{item['z_score']:+.2f} σ**（戦術上の大胆な割り切り、または攻略されやすいポイント）")


def _render_tactical_radar_chart(t_prof: Dict[str, Any]) -> None:
    """5大戦術柱のレーダーチャート（Plotly）."""
    radar_scores = t_prof.get("radar_scores", {})
    categories = list(radar_scores.keys())
    values = [float(v) for v in radar_scores.values()]

    if not categories:
        st.caption("レーダーチャートデータがありません。")
        return

    # 多角形を閉じるため先頭要素を末尾に追加
    categories_closed = categories + [categories[0]]
    values_closed = values + [values[0]]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=categories_closed,
        fill="toself",
        name=t_prof.get("team_name", "自クラブ"),
        fillcolor="rgba(31, 119, 180, 0.35)",
        line=dict(color="#1f77b4", width=2.5),
    ))

    # リーグ平均（50ptの基準線）
    avg_values = [50.0] * len(categories_closed)
    fig.add_trace(go.Scatterpolar(
        r=avg_values,
        theta=categories_closed,
        mode="lines",
        name="J1リーグ基準 (50)",
        line=dict(color="rgba(150, 150, 150, 0.7)", width=1.5, dash="dash"),
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(size=10),
            ),
        ),
        margin=dict(l=40, r=40, t=30, b=30),
        height=380,
        showlegend=True,
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_win_loss_bar_table(comparison_table: List[Dict[str, Any]]) -> None:
    """勝利時 vs 敗戦時の指標対比テーブルにインセルバーとギャップバッジを描画する."""
    if not comparison_table:
        return

    # ヘッダー
    h_name, h_win, h_loss, h_diff = st.columns([3.5, 3.2, 3.2, 2.1])
    h_name.caption("戦術指標")
    h_win.caption("勝利時 平均 (緑バー)")
    h_loss.caption("敗戦時 平均 (赤バー)")
    h_diff.caption("ギャップ (勝 - 敗)")
    st.markdown("<div style='margin-bottom: 6px; border-bottom: 1px solid #cbd5e1;'></div>", unsafe_allow_html=True)

    for row in comparison_table:
        label = row.get("metric_label", "")
        w_val = float(row.get("win_avg", 0.0))
        l_val = float(row.get("loss_avg", 0.0))
        diff = float(row.get("diff", 0.0))

        # バーの最大基準値
        max_v = max(abs(w_val), abs(l_val), 1.0)
        w_ratio = min(90.0, max(8.0, (abs(w_val) / max_v) * 90.0))
        l_ratio = min(90.0, max(8.0, (abs(l_val) / max_v) * 90.0))

        # 勝利時セルHTML
        w_html = f"""<div style="position: relative; width: 100%; min-height: 28px; background: #f8fafc; border-radius: 4px; overflow: hidden; padding: 3px 8px; border: 1px solid #e2e8f0; display: flex; align-items: center; box-sizing: border-box;">
  <div style="position: absolute; left: 0; top: 0; bottom: 0; width: {w_ratio}%; background: linear-gradient(90deg, rgba(34,197,94,0.18), rgba(22,163,74,0.30)); z-index: 1;"></div>
  <span style="position: relative; z-index: 2; font-weight: 700; font-size: 13px; color: #166534;">{w_val}</span>
</div>"""

        # 敗戦時セルHTML
        l_html = f"""<div style="position: relative; width: 100%; min-height: 28px; background: #f8fafc; border-radius: 4px; overflow: hidden; padding: 3px 8px; border: 1px solid #e2e8f0; display: flex; align-items: center; box-sizing: border-box;">
  <div style="position: absolute; left: 0; top: 0; bottom: 0; width: {l_ratio}%; background: linear-gradient(90deg, rgba(239,68,68,0.18), rgba(220,38,38,0.30)); z-index: 1;"></div>
  <span style="position: relative; z-index: 2; font-weight: 700; font-size: 13px; color: #991b1b;">{l_val}</span>
</div>"""

        # ギャップバッジ
        diff_color = "#16a34a" if diff > 0 else ("#dc2626" if diff < 0 else "#64748b")
        diff_bg = "#dcfce7" if diff > 0 else ("#fee2e2" if diff < 0 else "#f1f5f9")
        diff_sign = "+" if diff > 0 else ""
        diff_html = f"""<div style="padding-top: 4px; text-align: center;">
  <span style="display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 12.5px; background: {diff_bg}; color: {diff_color};">{diff_sign}{diff}</span>
</div>"""

        c_name, c_win, c_loss, c_diff = st.columns([3.5, 3.2, 3.2, 2.1])
        with c_name:
            st.markdown(f"<div style='font-size: 13px; font-weight: 600; color: #1e293b; padding-top: 5px;'>{label}</div>", unsafe_allow_html=True)
        with c_win:
            st.markdown(w_html, unsafe_allow_html=True)
        with c_loss:
            st.markdown(l_html, unsafe_allow_html=True)
        with c_diff:
            st.markdown(diff_html, unsafe_allow_html=True)

        st.markdown("<div style='margin: 3px 0; border-bottom: 1px solid #f1f5f9;'></div>", unsafe_allow_html=True)


def _render_win_loss_analysis_section(team_id: str) -> None:
    """勝ち筋・負け筋のスタッツ差分テーブルと分析テキスト."""
    wl = get_win_loss_pattern_analysis(team_id)
    if not wl.get("has_data"):
        st.caption("勝敗パターンデータが不足しています。")
        return

    st.write(
        f"**集計対象**: 勝利 **{wl['win_count']}** 試合 ｜ 敗戦 **{wl['loss_count']}** 試合 ｜ 引分 **{wl['draw_count']}** 試合"
    )

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.success("**【勝ちやすい試合展開（勝ち筋）】**")
        for take in wl.get("win_takeaways", []):
            st.markdown(f"- {take}")
    with col_t2:
        st.error("**【負けやすい試合展開（負け筋・攻略要因）】**")
        for take in wl.get("loss_takeaways", []):
            st.markdown(f"- {take}")

    st.write("")
    st.markdown("##### 勝利時 vs 敗戦時の指標対比テーブル")
    comp_table = wl.get("comparison_table", [])
    if comp_table:
        _render_win_loss_bar_table(comp_table)


def _render_style_adherence_section(team_id: str) -> None:
    """スタイル合致度 Top 3 試合カード & 試合ページへのディープリンク."""
    best_matches = get_style_adherence_matches(team_id)
    if not best_matches:
        st.caption("該当する試合データがありません。")
        return

    cols = st.columns(3)
    for idx, m in enumerate(best_matches):
        with cols[idx]:
            with st.container(border=True):
                st.markdown(f"##### 第{m['section']}節 vs {m['opponent']}")
                st.markdown(f"**スコア**: `{m['score']}` ｜ **体現度**: :orange[**{m['style_score']} pt**]")
                st.caption(f"**戦況スタッツ**: {m['key_stats']}")
                st.info(f"💡 {m['reason']}")
                if st.button("⚽ 試合詳細を観る ❯", key=f"btn_adhere_match_{m['match_id']}"):
                    navigate_to(view=VIEW_MATCH, match_id=m["match_id"])


def _render_goal_and_time_dynamics_section(team_id: str) -> None:
    """得点経路割合 & 15分ごとの得失点推移."""
    goal_data = get_goal_pattern_breakdown(team_id)
    time_segments = goal_data.get("time_segments", {})
    path_breakdown = goal_data.get("path_breakdown", {})

    col_g1, col_g2 = st.columns([1, 1])

    with col_g1:
        st.markdown("##### ⚽ ゴール創出経路の傾向")
        for path_name, pct in path_breakdown.items():
            st.write(f"**{path_name}**: `{pct}%`")
            st.progress(min(1.0, float(pct) / 100.0))

    with col_g2:
        st.markdown("##### ⏱️ 15分時間帯別の得点・失点ダイナミクス")
        if time_segments:
            labels = list(time_segments.keys())
            goals_for = [
                time_segments[k].get(
                    "team_goals",
                    time_segments[k].get(
                        "goals_for",
                        time_segments[k].get(f"{team_id.lower()}_goals", 0),
                    ),
                )
                for k in labels
            ]
            goals_against = [
                time_segments[k].get(
                    "opp_goals",
                    time_segments[k].get("goals_against", 0),
                )
                for k in labels
            ]

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=labels,
                y=goals_for,
                name="得点",
                marker_color="#2ca02c",
            ))
            fig.add_trace(go.Bar(
                x=labels,
                y=goals_against,
                name="失点",
                marker_color="#d62728",
            ))
            fig.update_layout(
                barmode="group",
                margin=dict(l=30, r=20, t=20, b=30),
                height=260,
                xaxis_title="時間帯（分）",
                yaxis_title="ゴール数",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("時間帯データがありません。")


def _render_cross_analytics_section(team_id: str) -> None:
    """CB/DHユニット相性 ＆ 相手守備タイプ別耐性."""
    synthesis = load_team_season_synthesis(team_id)
    if not synthesis:
        st.caption("クロス集計データがありません。")
        return

    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.markdown("##### 🛡️ センターバック (CB) ユニット相性")
        cb_units = synthesis.get("starter_unit_synergy", {}).get("center_back_units", [])
        for unit in cb_units[:3]:
            with st.container(border=True):
                st.markdown(f"**{unit['unit_name']}**")
                st.write(
                    f"出場: `{unit['matches_played']}試合` ｜ 勝率: **`{unit['win_rate_pct']}%`** ｜ 平均xPTS: `{unit['avg_xpts']}`"
                )
                st.caption(f"陣形コンパクトネス: 平均凸包面積 `{unit['avg_convex_hull_m2']:.1f} ㎡`")

    with col_c2:
        st.markdown("##### ⚔️ 対戦相手の守備タイプ別耐性")
        archetypes = synthesis.get("opponent_archetype_resistance", {})
        arch_names = {
            "HIGH_PRESS": "ハイプレス志向型",
            "MID_BLOCK": "ミドルブロック陣形型",
            "LOW_BLOCK": "低重心ブロック・撤退カウンター型",
        }
        for arch_key, a_info in archetypes.items():
            with st.container(border=True):
                st.markdown(f"**{arch_names.get(arch_key, arch_key)}** ({a_info.get('match_count', 0)}試合)")
                st.write(
                    f"勝率: **`{a_info.get('win_rate_pct', 0)}%`** ｜ 平均xPTS: `{a_info.get('avg_xpts', 0)}` ｜ BPI前進力: `{a_info.get('avg_bpi', 0)}`"
                )
                st.caption(
                    f"PA進入率: `{a_info.get('avg_conv_30_to_pa_pct', 0)}%` ｜ クロス依存度: `{a_info.get('avg_cross_reliance_pct', 0)}%`"
                )


def _build_metric_rank_badge_style(rank: int) -> Tuple[str, str]:
    """順位に応じた背景色と文字色のスタイルタプルを返す."""
    if rank == 1:
        return "#fef3c7", "#b45309"
    elif rank <= 3:
        return "#e0e7ff", "#3730a3"
    elif rank <= 6:
        return "#ecfdf5", "#047857"
    elif rank <= 12:
        return "#f1f5f9", "#334155"
    else:
        return "#f8fafc", "#64748b"


def _build_metric_bar_cell_html(item: Dict[str, Any]) -> str:
    """インセル・プログレスバー背景と順位バッジを持つHTML文字列を生成する."""
    val = item.get("season_avg", 0.0)
    bar_ratio = float(item.get("bar_ratio", 50.0))
    rank = int(item.get("rank", 10))
    total_teams = int(item.get("total_teams", 20))
    bg_color, text_color = _build_metric_rank_badge_style(rank)

    cur_tier = item.get("current_tier", {})
    level = cur_tier.get("level", "B").split()[0]  # "S", "A", "B", "C", "D"

    if rank <= 3:
        bar_gradient = "linear-gradient(90deg, rgba(37,99,235,0.28), rgba(59,130,246,0.40))"
    else:
        bar_gradient = "linear-gradient(90deg, rgba(59,130,246,0.16), rgba(96,165,250,0.26))"

    html = f"""<div style="position: relative; width: 100%; min-height: 32px; background: #f8fafc; border-radius: 6px; overflow: hidden; padding: 4px 10px; border: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; box-sizing: border-box; margin-top: 3px;">
  <div style="position: absolute; left: 0; top: 0; bottom: 0; width: {bar_ratio}%; background: {bar_gradient}; z-index: 1;"></div>
  <span style="position: relative; z-index: 2; font-weight: 700; font-size: 13.5px; color: #0f172a; white-space: nowrap;">{val}</span>
  <span style="position: relative; z-index: 2; font-size: 11.5px; font-weight: 700; padding: 2px 7px; border-radius: 4px; background: {bg_color}; color: {text_color}; border: 1px solid rgba(0,0,0,0.06); white-space: nowrap;">{rank}位/{total_teams} <span style="opacity: 0.85;">({level})</span></span>
</div>"""
    return html


def _render_metric_dialog_body(item: Dict[str, Any]) -> None:
    """戦術指標モーダルダイアログの本文を描画する (5倍詳細解説・5段階基準数値幅・J1比較)."""
    cur_tier = item.get("current_tier", {})
    stars = cur_tier.get("stars", "★★★☆☆")
    level = cur_tier.get("level", "B")

    st.subheader(f"{item['metric_name']}")
    st.markdown(
        f"**現在のJ1評価**: :orange[{stars}] **{level}** ｜ 実績値: `{item.get('season_avg')}` （**J1 {item.get('rank')}位** / {item.get('total_teams', 20)}クラブ）",
    )
    st.markdown("---")

    # 1. 戦術の概要 (5倍詳細解説)
    st.markdown("#### 📌 戦術の概要とピッチ上の影響")
    st.info(item.get("description", "戦術的指標の計測値です。"))

    # 2. 5段階の基準数値幅と判定基準
    st.markdown("#### 🎯 指標の5段階判定基準 (目安数値幅)")
    five_tiers = item.get("five_tier_scale", [])
    if five_tiers:
        for t in five_tiers:
            is_current = (t.get("tier") == cur_tier.get("tier"))
            highlight_style = (
                "border-left: 4px solid #2563eb; background: #eff6ff; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;"
                if is_current
                else "background: #f8fafc; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e2e8f0;"
            )
            current_tag = (
                " <span style='background: #2563eb; color: #fff; font-size: 11px; padding: 2px 7px; border-radius: 3px; font-weight: 700;'>👈 該当チームの現在値</span>"
                if is_current
                else ""
            )
            st.markdown(
                f"""<div style="{highlight_style}">
  <strong>{t.get('stars')} {t.get('level')}</strong> 【{t.get('range')}】{current_tag}<br>
  <span style="font-size: 12.5px; color: #475569; line-height: 1.5;">{t.get('description')}</span>
</div>""",
                unsafe_allow_html=True,
            )
    else:
        st.success(item.get("standard_val", "リーグ標準水準を参照"))

    # 3. リーグ最高値、平均値、該当チームの値
    st.markdown("#### 📊 J1リーグ比較サマリー")
    c1, c2, c3 = st.columns(3)
    with c1:
        best_label = "🏆 J1最良値" if item.get("lower_is_better") else "🏆 J1最高値"
        st.metric(
            label=best_label,
            value=f"{item.get('best_val')}",
            help=f"達成クラブ: {item.get('best_team_name')}",
        )
        st.caption(f"達成: **{item.get('best_team_name')}**")
    with c2:
        st.metric(
            label="📈 J1平均値",
            value=f"{item.get('league_avg')}",
        )
    with c3:
        st.metric(
            label="📍 該当チーム",
            value=f"{item.get('season_avg')}",
        )
        st.caption(f"順位: **{item.get('rank')}位** / 20クラブ")

    st.write("")
    if st.button("閉じる", key=f"btn_close_dialog_{item['metric_name']}", use_container_width=True):
        st.rerun()


@st.dialog("📖 戦術指標 詳細解説", width="large")
def _show_metric_detail_dialog(item: Dict[str, Any]) -> None:
    """戦術指標の「？」ボタン選択時にモーダルダイアログを開く."""
    _render_metric_dialog_body(item)


def _inject_metric_table_custom_css() -> None:
    """指標テーブルの縦崩れを防止し、丸い「？」ボタンを指標名直後にインライン配置するためのCSSを注入する."""
    st.markdown(
        """
        <style>
        /* モバイル幅でも指標カードの上段とタイトル＋ボタンは絶対に折り返さず横並びを維持 */
        div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            flex-direction: row !important;
        }

        div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"] [data-testid="stColumn"] {
            min-width: 0 !important;
        }

        /* 指標名と丸い？ボタンのstHorizontalBlock: テキスト直後にピッタリ配置 */
        div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"]:has(button) {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 6px !important;
            width: 100% !important;
        }
        div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"]:has(button) > [data-testid="stColumn"]:first-child {
            flex: 0 0 auto !important;
            width: auto !important;
            min-width: 0 !important;
            max-width: fit-content !important;
        }
        div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"]:has(button) > [data-testid="stColumn"]:last-child {
            flex: 0 0 24px !important;
            width: 24px !important;
            min-width: 24px !important;
            max-width: 24px !important;
        }

        /* Streamlitのモバイル用メディアクエリ (min-width: calc(100% - ...)) を完全上書き */
        @media (max-width: 768px) {
            div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"] {
                flex-wrap: nowrap !important;
            }
            div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"] [data-testid="stColumn"] {
                min-width: 0 !important;
                width: auto !important;
            }
            div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"]:has(button) {
                flex-wrap: nowrap !important;
            }
            div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"]:has(button) > [data-testid="stColumn"]:first-child {
                flex: 0 0 auto !important;
                width: auto !important;
                min-width: 0 !important;
                max-width: fit-content !important;
            }
            div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"]:has(button) > [data-testid="stColumn"]:last-child {
                flex: 0 0 24px !important;
                width: 24px !important;
                min-width: 24px !important;
                max-width: 24px !important;
            }
        }

        /* エキスパンダー内のすべてのボタンを完全な円形（丸い？ボタン）にする */
        div[data-testid="stExpanderDetails"] button {
            width: 20px !important;
            min-width: 20px !important;
            max-width: 20px !important;
            height: 20px !important;
            min-height: 20px !important;
            max-height: 20px !important;
            border-radius: 50% !important;
            padding: 0 !important;
            margin: 0 !important;
            font-size: 11px !important;
            font-weight: 700 !important;
            line-height: 18px !important;
            color: #2563eb !important;
            background-color: #eff6ff !important;
            border: 1.5px solid #93c5fd !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            cursor: pointer !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.06) !important;
        }
        div[data-testid="stExpanderDetails"] button:hover {
            background-color: #2563eb !important;
            color: #ffffff !important;
            border-color: #2563eb !important;
        }
        div[data-testid="stExpanderDetails"] button p,
        div[data-testid="stExpanderDetails"] button div {
            margin: 0 !important;
            padding: 0 !important;
            font-size: 11px !important;
            font-weight: 700 !important;
            line-height: 18px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_metric_row(item: Dict[str, Any]) -> None:
    """全55戦術指標の1指標分を2段カード形式で描画する (モバイル最適化・指標名直後に丸い？ボタン)."""
    cur_tier = item.get("current_tier", {})
    stars = cur_tier.get("stars", "★★★☆☆")
    level = cur_tier.get("level", "B").split()[0]
    latest = item.get("latest_val", "-")
    avg = item.get("league_avg", "-")

    # 上段: [指標名 + 評価] [?] ｜ [直近節値 ＆ J1平均]
    c_top_left, c_top_right = st.columns([2.6, 1.4], vertical_alignment="center")

    with c_top_left:
        c_title, c_btn = st.columns([0.85, 0.15], vertical_alignment="center")
        with c_title:
            st.markdown(
                f"<div style='display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; line-height: 1.3;'>"
                f"<span style='font-size: 13.5px; font-weight: 700; color: #1e293b;'>{item['metric_name']}</span>"
                f"<span style='font-size: 11px; font-weight: 700; color: #d97706;'>{stars[:3]} ({level})</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with c_btn:
            if st.button("?", key=f"btn_help_{item['metric_name']}", help="戦術指標の詳細解説と5段階判定基準をダイアログで表示"):
                _show_metric_detail_dialog(item)

    with c_top_right:
        st.markdown(
            f"<div style='font-size: 11.5px; color: #64748b; text-align: right; line-height: 1.4; white-space: nowrap;'>"
            f"直近: <b style='color: #1e293b;'>{latest}</b> ｜ 平均: {avg}</div>",
            unsafe_allow_html=True,
        )

    # 下段: 横幅100%のインセルプログレスバー (モバイルでも文字重なり・順位見切れなし)
    bar_html = _build_metric_bar_cell_html(item)
    st.markdown(bar_html, unsafe_allow_html=True)


def _render_metric_category_table(category_name: str, metrics: List[Dict[str, Any]]) -> None:
    """1つのカテゴリ内の指標一覧を描画する (モバイル最適化2段カード構成)."""
    st.caption("💡 指標名横の「？」ボタンで5段階評価基準と詳細解説を表示できます。バー内はシーズン平均値とJ1順位です。")
    st.markdown("<div style='margin-bottom: 8px; border-bottom: 1px solid #cbd5e1;'></div>", unsafe_allow_html=True)

    for item in metrics:
        _render_metric_row(item)
        st.markdown("<div style='margin: 8px 0; border-bottom: 1px solid #f1f5f9;'></div>", unsafe_allow_html=True)


def _render_55_metrics_expander_section(team_id: str) -> None:
    """全55戦術指標の6大カテゴリ別エキスパンダーテーブル（相対バー・ランク・詳細ダイアログボタン付き）."""
    _inject_metric_table_custom_css()
    categorized = get_team_55_metrics_categorized(team_id)
    if not categorized:
        st.caption("55戦術指標データがありません。")
        return

    st.caption("ℹ️ 各指標名の横の「？」ボタンを押すと、戦術概要・5段階基準数値幅・J1最良値・平均値の解説ダイアログを確認できます。セル内のバーはJ1トップを90%とした相対度合いを示します。")

    for cat_title, metrics_list in categorized.items():
        with st.expander(f"{cat_title} ({len(metrics_list)}指標)"):
            if metrics_list:
                _render_metric_category_table(cat_title, metrics_list)


# ===========================================================================
# 4. タブ2: 所属選手 & CBPリーダー
# ===========================================================================
def _render_squad_tab(team_id: str) -> None:
    """所属選手一覧とCBPリーダーボード."""
    st.subheader("👤 所属選手一覧 ＆ チャンスビルディングポイント (CBP)")
    st.caption("選手を選択すると、選手個人の詳細プロファイル（節別スタッツ推移・採点寸評履歴）へジャンプします。")

    squad = get_team_squad_cbp(team_id)
    if not squad:
        st.info("選手スタッツデータが登録されていません。")
        return

    # ポジションフィルタ ＆ ソート
    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        pos_filter = st.radio(
            "ポジション絞り込み",
            options=["ALL", "FW", "MF", "DF", "GK"],
            horizontal=True,
            key="squad_pos_filter",
        )
    with col_f2:
        sort_metric = st.selectbox(
            "並び替え基準",
            options=["total_cbp", "goals", "assists", "minutes", "sprints"],
            format_func=lambda k: {
                "total_cbp": "CBP総合ポイント順",
                "goals": "得点数順",
                "assists": "アシスト数順",
                "minutes": "総出場時間順",
                "sprints": "スプリント回数順",
            }.get(k, k),
            key="squad_sort_metric",
        )

    # フィルタリング & ソート
    filtered = squad if pos_filter == "ALL" else [p for p in squad if p["position"] == pos_filter]
    filtered.sort(key=lambda p: p.get(sort_metric, 0), reverse=True)

    st.write(f"該当選手数: **{len(filtered)}** 名")

    # グリッド表示（2列で選手写真を大きく美麗に表示）
    cols = st.columns(2)
    for idx, p in enumerate(filtered):
        with cols[idx % 2]:
            with st.container(border=True):
                col_img, col_info = st.columns([1.2, 2.0])
                with col_img:
                    photo_url = p.get("photo_url")
                    if photo_url:
                        st.markdown(
                            f'<div style="text-align: center; padding: 4px;">'
                            f'<img src="{photo_url}" style="width: 145px; max-width: 100%; height: auto; border-radius: 8px; filter: drop-shadow(0 4px 6px rgba(0,0,0,0.12));">'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<div style='width:120px;height:145px;background:#f1f5f9;border-radius:8px;"
                            "display:flex;align-items:center;justify-content:center;font-size:42px;margin:auto;'>👤</div>",
                            unsafe_allow_html=True,
                        )
                with col_info:
                    st.markdown(f"### {p['player_name']}")
                    yomi_str = p.get("yomi", "")
                    en_str = p.get("en_name", "")
                    if yomi_str and yomi_str != p["player_name"]:
                        sub_text = f"よみがな: **{yomi_str}**"
                        if en_str and en_str.lower() != yomi_str.lower():
                            sub_text += f" ({en_str})"
                        st.caption(sub_text)
                    elif en_str:
                        st.caption(f"表記: **{en_str}**")

                    st.markdown(f"`{p['position']}` **#{p['number']}** ｜ `{p['matches']}試合` ({p['minutes']}分)")
                    st.write(f"得点: **`{p['goals']}`** ｜ 助攻: **`{p['assists']}`** ｜ 走力: `{p['sprints']}回`")
                    st.markdown(f"**CBP総合**: :blue-background[**{p['total_cbp']} pt**]")
                    st.write("")
                    if st.button("👤 選手詳細を見る ❯", key=f"btn_squad_p_{p['player_id']}_{idx}", use_container_width=True):
                        navigate_to(
                            view=VIEW_PLAYER,
                            team_id=team_id,
                            player_id=p["player_id"],
                            player_name=p["player_name"],
                        )


# ===========================================================================
# 5. タブ3: 他クラブ直接対比 (Head-to-Head)
# ===========================================================================
def _render_h2h_tab(team_id: str) -> None:
    """他クラブとの直接対比タブ."""
    st.subheader("⚔️ 他クラブとの直接対比 (Head-to-Head Comparison)")
    st.caption("比較対象クラブを選択すると、戦術レーダーチャートの重畳表示、主要10指標の比較、および今季の直接対決実績を表示します。")

    other_teams = [t for t in TEAM_ID_MAP.keys() if t != team_id]
    current_target = st.session_state.get("h2h_target_team_id")
    default_idx = other_teams.index(current_target) if current_target in other_teams else 0

    col_sel, _ = st.columns([2, 3])
    with col_sel:
        target_team = st.selectbox(
            "対戦・比較対象クラブを選択",
            options=other_teams,
            index=default_idx,
            format_func=lambda tid: f"{resolve_team_name(tid)} ({tid})",
            key="h2h_target_selector",
        )
    st.session_state["h2h_target_team_id"] = target_team

    # 両クラブのエンブレム＆指揮官バナー
    mgr1 = get_team_manager_info(team_id)
    mgr2 = get_team_manager_info(target_team)
    mgr_av1 = get_team_manager_avatar_html(team_id, size=40)
    mgr_av2 = get_team_manager_avatar_html(target_team, size=40)

    col_em1, col_vs, col_em2 = st.columns([4, 1, 4])
    with col_em1:
        st.markdown(
            f"<div style='display: flex; align-items: center; justify-content: space-between; background: rgba(59, 130, 246, 0.08); padding: 10px 14px; border-radius: 8px;'>"
            f"  <div style='display: flex; align-items: center; gap: 10px;'>"
            f"    {get_team_emblem_html(team_id, width=44, height=44)}"
            f"    <div><strong style='font-size: 1.05rem; color: #1e3a8a;'>{resolve_team_name(team_id)}</strong><br><span style='font-size: 0.8rem; color: #64748b;'>自クラブ (青)</span></div>"
            f"  </div>"
            f"  <div style='display: flex; align-items: center; gap: 8px;'>"
            f"    <div style='text-align: right;'><span style='font-size: 0.75rem; color: #64748b;'>指揮官</span><br><b style='font-size: 0.85rem;'>{mgr1.get('manager_name')}</b></div>"
            f"    {mgr_av1}"
            f"  </div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_vs:
        st.markdown(
            "<div style='text-align: center; font-size: 1.5rem; font-weight: 800; color: #94a3b8; line-height: 52px;'>VS</div>",
            unsafe_allow_html=True,
        )
    with col_em2:
        st.markdown(
            f"<div style='display: flex; align-items: center; justify-content: space-between; background: rgba(249, 115, 22, 0.08); padding: 10px 14px; border-radius: 8px;'>"
            f"  <div style='display: flex; align-items: center; gap: 8px;'>"
            f"    {mgr_av2}"
            f"    <div style='text-align: left;'><span style='font-size: 0.75rem; color: #64748b;'>指揮官</span><br><b style='font-size: 0.85rem;'>{mgr2.get('manager_name')}</b></div>"
            f"  </div>"
            f"  <div style='display: flex; align-items: center; gap: 10px;'>"
            f"    <div style='text-align: right;'><strong style='font-size: 1.05rem; color: #7c2d12;'>{resolve_team_name(target_team)}</strong><br><span style='font-size: 0.8rem; color: #64748b;'>比較クラブ (橙)</span></div>"
            f"    {get_team_emblem_html(target_team, width=44, height=44)}"
            f"  </div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.write("")

    # 比較データ取得
    h2h_data = get_team_h2h_comparison(team_id, target_team)

    col_r, col_tbl = st.columns([1, 1])

    with col_r:
        st.markdown(f"##### 🎯 戦術スタイル レーダー重畳比較")
        _render_h2h_radar_chart(h2h_data)

    with col_tbl:
        st.markdown(f"##### 📊 主要10戦術指標 直接対比")
        stat_comps = h2h_data.get("stat_comparisons", [])
        if stat_comps:
            df_h2h = pd.DataFrame(stat_comps)
            df_h2h.columns = ["戦術指標", f"{resolve_team_name(team_id)}", f"{resolve_team_name(target_team)}", "差分"]
            st.dataframe(df_h2h, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("##### ⚔️ 今季の直接対決実績")
    direct_matches = h2h_data.get("direct_matches", [])
    if direct_matches:
        for dm in direct_matches:
            with st.container(border=True):
                h_name = resolve_team_name(dm["home_team_id"])
                a_name = resolve_team_name(dm["away_team_id"])
                st.markdown(
                    f"**{dm['date']}** ＠ {dm.get('stadium', 'スタジアム')} ｜ "
                    f"**{h_name}** `{dm['home_score']} - {dm['away_score']}` **{a_name}**"
                )
                if st.button("⚽ この試合の5大セクション分析を見る ❯", key=f"btn_h2h_match_{dm['match_id']}"):
                    navigate_to(view=VIEW_MATCH, match_id=dm["match_id"])
    else:
        st.info("今季の直接対決データはまだありません（未対戦）。")


def _render_h2h_radar_chart(h2h_data: Dict[str, Any]) -> None:
    """2クラブの戦術スタイルレーダーのオーバーレイ表示."""
    t_a = h2h_data["team_a"]
    t_b = h2h_data["team_b"]

    radar_a = t_a.get("radar", {})
    radar_b = t_b.get("radar", {})

    categories = list(radar_a.keys())
    if not categories:
        st.caption("比較レーダーデータがありません。")
        return

    cat_closed = categories + [categories[0]]
    val_a_closed = [float(radar_a.get(c, 50.0)) for c in categories] + [float(radar_a.get(categories[0], 50.0))]
    val_b_closed = [float(radar_b.get(c, 50.0)) for c in categories] + [float(radar_b.get(categories[0], 50.0))]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=val_a_closed,
        theta=cat_closed,
        fill="toself",
        name=t_a["name"],
        fillcolor="rgba(31, 119, 180, 0.3)",
        line=dict(color="#1f77b4", width=2.5),
    ))

    fig.add_trace(go.Scatterpolar(
        r=val_b_closed,
        theta=cat_closed,
        fill="toself",
        name=t_b["name"],
        fillcolor="rgba(255, 127, 14, 0.3)",
        line=dict(color="#ff7f0e", width=2.5),
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(size=9),
            ),
        ),
        margin=dict(l=30, r=30, t=20, b=20),
        height=360,
        showlegend=True,
    )

    st.plotly_chart(fig, use_container_width=True)
