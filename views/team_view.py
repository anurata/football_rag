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

from agent.objective_profiler import resolve_team_name, TEAM_NAME_MAP
from agent.qa_engine import TacticalQAEngine
from pipeline.league_overview_data import get_league_standings
from pipeline.team_analytics_engine import (
    compute_all_teams_clusters,
    get_goal_pattern_breakdown,
    get_style_adherence_matches,
    get_team_55_metrics_categorized,
    get_team_h2h_comparison,
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
def _render_team_selector() -> str:
    """分析対象クラブ選択プルダウン."""
    team_keys = list(TEAM_NAME_MAP.keys())
    current_team = st.session_state.get("selected_team_id")
    default_idx = team_keys.index(current_team) if current_team in team_keys else 0

    col_sel, _ = st.columns([2, 3])
    with col_sel:
        selected_team = st.selectbox(
            "分析対象クラブを選択",
            options=team_keys,
            index=default_idx,
            format_func=lambda tid: f"{resolve_team_name(tid)} ({tid})",
            key="team_view_selector",
        )
    st.session_state["selected_team_id"] = selected_team
    return selected_team


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
    s_info = next((s for s in standings if s["team_id"] == team_id), None)
    rank_str = f"J1 第{s_info['rank']}位" if s_info else "J1"
    pts_str = f"{s_info['pts']} pts" if s_info else "-"
    form_badges = s_info.get("form", ["W", "W", "W", "D", "W"]) if s_info else []

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown(f"## 🛡️ {team_name} ({team_id})")
        st.markdown(
            f"**{rank_str}** ({pts_str}) ｜ 指揮官: **{manager}** ｜ 基本布陣: **`{base_f}`**"
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
        df_comp = pd.DataFrame(comp_table)[["metric_label", "win_avg", "loss_avg", "diff"]]
        df_comp.columns = ["戦術指標", "勝利時 平均", "敗戦時 平均", "ギャップ (勝-敗)"]
        st.dataframe(df_comp, use_container_width=True, hide_index=True)


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
            goals_for = [time_segments[k].get("goals_for", 0) for k in labels]
            goals_against = [time_segments[k].get("goals_against", 0) for k in labels]

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


def _render_55_metrics_expander_section(team_id: str) -> None:
    """全55指標の6大カテゴリ別エキスパンダーテーブル."""
    categorized = get_team_55_metrics_categorized(team_id)
    if not categorized:
        st.caption("55戦術指標データがありません。")
        return

    for cat_title, metrics_list in categorized.items():
        with st.expander(f"{cat_title} ({len(metrics_list)}指標)"):
            if metrics_list:
                df = pd.DataFrame(metrics_list)
                df.columns = ["戦術指標名", "シーズン平均値", "直近節値", "J1リーグ平均"]
                st.dataframe(df, use_container_width=True, hide_index=True)


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

    # グリッド表示（3列）
    cols = st.columns(3)
    for idx, p in enumerate(filtered):
        with cols[idx % 3]:
            with st.container(border=True):
                st.markdown(f"##### {p['player_name']} ({p['position']} #{p['number']})")
                st.write(
                    f"出場: `{p['matches']}試合` (`{p['minutes']}分`) ｜ 得点: **`{p['goals']}`** ｜ 助攻: **`{p['assists']}`**"
                )
                st.markdown(f"**CBP総合**: :blue-background[**{p['total_cbp']} pt**] ｜ スプリント: `{p['sprints']}回`")
                if st.button("👤 選手詳細を見る ❯", key=f"btn_squad_p_{p['player_id']}_{idx}"):
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

    other_teams = [t for t in TEAM_NAME_MAP.keys() if t != team_id]
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
