"""
views/league_view.py

1. J-League League Overview page (standings, expected points, matchweek cards,
rankings, and 4-quadrant tactical positioning map).
Provides deep-linking to team, match, and player views, and ubiquitous AI QA integration.
"""

from typing import Any, Dict, List, Optional
import plotly.graph_objects as go
import streamlit as st

from agent.qa_engine import TacticalQAEngine
from pipeline.league_overview_data import (
    get_available_seasons,
    get_league_standings,
    get_league_stats_rankings,
    get_matchweek_matches,
    get_matchweek_report_cards,
    get_tactical_positioning_map_data,
)
from pipeline.team_analytics_engine import (
    get_team_emblem_html,
    get_team_emblem_url,
)
from views.components.ai_modal import render_ai_button
from views.components.match.report_card_section import (
    _get_rank_badge_html,
    _RANK_COLORS,
)
from views.navigation import (
    VIEW_LEAGUE,
    VIEW_MATCH,
    VIEW_PLAYER,
    VIEW_TEAM,
    navigate_to,
)


@st.cache_data(ttl=600)
def _load_standings_data(season: int) -> List[Dict[str, Any]]:
    """Cached loader for league standings."""
    return get_league_standings(season=season)


@st.cache_data(ttl=600)
def _load_matchweek_data(season: int, matchweek: Optional[int]) -> Dict[str, Any]:
    """Cached loader for matchweek schedule and cards."""
    return get_matchweek_matches(season=season, matchweek=matchweek)


@st.cache_data(ttl=600)
def _load_matchweek_report_cards(season: int, matchweek: Optional[int]) -> Dict[str, Any]:
    """Cached loader for matchweek report cards (all 20 clubs)."""
    return get_matchweek_report_cards(season=season, matchweek=matchweek)


@st.cache_data(ttl=600)
def _load_rankings_data(season: int) -> Dict[str, Any]:
    """Cached loader for team and player statistical leaderboards."""
    return get_league_stats_rankings(season=season, top_n=5)


@st.cache_data(ttl=600)
def _load_tactical_map_data(season: int, metric_preset: str) -> Dict[str, Any]:
    """Cached loader for tactical positioning map coordinates."""
    return get_tactical_positioning_map_data(season=season, metric_preset=metric_preset)


def _render_form_badge(form_list: List[str]) -> str:
    """Return formatted HTML/Markdown string for Form W/D/L badges."""
    if not form_list:
        return "―"
    badges = []
    for res in form_list:
        if res == "W":
            badges.append("🟢勝")
        elif res == "D":
            badges.append("⚪分")
        else:
            badges.append("🔴負")
    return " ".join(badges)


def _render_standings_card(team: Dict[str, Any]) -> None:
    """Render a single club standings card with official emblem."""
    with st.container(border=True):
        col_rank, col_emblem, col_name = st.columns([1, 1, 4])
        with col_rank:
            rank = team.get("rank", 1)
            medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"#{rank}"))
            st.markdown(f"### {medal}")
        with col_emblem:
            tid = team.get("team_id", "")
            st.markdown(
                f"<div style='text-align: center; padding-top: 4px;'>"
                f"{get_team_emblem_html(tid, width=38, height=38)}"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_name:
            st.markdown(f"**{team.get('name', 'チーム')}**")
            st.caption(f"消化: {team.get('played', 0)}試合 | {team.get('won', 0)}勝{team.get('drawn', 0)}分{team.get('lost', 0)}敗")

        # Stats metrics row
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric(label="実勝点", value=f"{team.get('points', 0)}pt")
        with c2:
            st.metric(label="得失点", value=f"{team.get('gd', 0):+d}")
        with c3:
            st.metric(label="xPTS", value=f"{team.get('xpts_total', 0.0):.1f}")
        with c4:
            luck = team.get("luck_index", 0.0)
            luck_sign = f"{luck:+0.1f}"
            st.metric(label="運指数", value=luck_sign)

        # Form row & deep link
        col_form, col_btn = st.columns([2, 1])
        with col_form:
            form_str = _render_form_badge(team.get("form", []))
            st.caption(f"直近調子 (Form): {form_str}")
        with col_btn:
            tid = team.get("team_id", "")
            if st.button("クラブ詳細 ❯", key=f"btn_team_{tid}", use_container_width=True):
                navigate_to(view=VIEW_TEAM, team_id=tid)


def _render_standings_section(
    season: int,
    standings: List[Dict[str, Any]],
    qa_engine: TacticalQAEngine,
) -> None:
    """Section 1: Latest standings & expected points (cards view)."""
    col_title, col_ai = st.columns([3, 1])
    with col_title:
        st.subheader("📊 1. 最新順位表 ＆ 期待値 (xPTS / xG / xGA)")
        st.caption("全20クラブの順位・勝点に加え、ポアソンモデルによる期待勝点（xPTS）と運指数（勝点 - xPTS）を表示します。")
    with col_ai:
        render_ai_button(
            button_key="ai_btn_standings",
            view_type=VIEW_LEAGUE,
            qa_engine=qa_engine,
            section_key="standings",
            note="Jリーグ順位表・xPTS期待値と運指数について分析",
            button_label="🤖 順位表をAI分析",
        )

    if not standings:
        st.info("順位表データが見つかりません。")
        return

    # Render clubs in a 2-column responsive grid
    col_left, col_right = st.columns(2)
    for idx, team in enumerate(standings):
        target_col = col_left if idx % 2 == 0 else col_right
        with target_col:
            _render_standings_card(team)


def _render_match_card(m: Dict[str, Any]) -> None:
    """Render a single match card in matchweek view."""
    with st.container(border=True):
        col_hdr, col_score = st.columns([3, 2])
        with col_hdr:
            st.markdown(f"**{m.get('home_team_name', '')} vs {m.get('away_team_name', '')}**")
            st.caption(f"📅 {m.get('date', '')} | 🏟️ {m.get('stadium', 'スタジアム')}")
        with col_score:
            if m.get("is_finished", False):
                h_score = m.get("home_score", 0)
                a_score = m.get("away_score", 0)
                st.markdown(f"### `{h_score} - {a_score}`")
                h_xg = m.get("home_xg")
                a_xg = m.get("away_xg")
                if h_xg is not None and a_xg is not None:
                    st.caption(f"xG: `{h_xg:.2f}` - `{a_xg:.2f}`")
            else:
                st.markdown("### `試合前`")

        # Links and deep link button
        col_ext, col_nav = st.columns([2, 1])
        with col_ext:
            links = []
            yt_url = m.get("youtube_url")
            if yt_url:
                links.append(f"[📺 ハイライト]({yt_url})")
            rep_url = m.get("official_report_url")
            if rep_url:
                links.append(f"[📋 公式戦評]({rep_url})")
            if links:
                st.markdown(" • ".join(links))
        with col_nav:
            mid = m.get("match_id", "")
            if st.button("試合詳細 ❯", key=f"btn_match_{mid}", use_container_width=True):
                navigate_to(view=VIEW_MATCH, match_id=mid)


def _render_matchweek_section(
    season: int,
    qa_engine: TacticalQAEngine,
) -> None:
    """Section 2: Matchweek schedule and match cards."""
    col_title, col_ai = st.columns([3, 1])
    with col_title:
        st.subheader("⚽ 2. 節別日程 ＆ 全節試合カード")
        st.caption("節を選択して対戦カード・スコア・xG・公式外部リンクを閲覧できます。カードから該当試合の深層分析へ遷移可能です。")
    with col_ai:
        render_ai_button(
            button_key="ai_btn_matchweek",
            view_type=VIEW_LEAGUE,
            qa_engine=qa_engine,
            section_key="matchweek",
            note="節別の日程・対戦カード・ハイライトについて分析",
            button_label="🤖 日程カードをAI分析",
        )

    # Initial probe to get available matchweeks
    meta_info = _load_matchweek_data(season=season, matchweek=None)
    available_weeks = meta_info.get("available_matchweeks", [])
    if not available_weeks:
        st.info("日程データが登録されていません。")
        return

    default_week = meta_info.get("selected_matchweek", available_weeks[0])
    selected_week = st.selectbox(
        "表示する節を選択",
        options=available_weeks,
        index=available_weeks.index(default_week) if default_week in available_weeks else 0,
        format_func=lambda w: f"第 {w} 節",
        key=f"sb_matchweek_selector_{season}",
    )

    mw_data = _load_matchweek_data(season=season, matchweek=selected_week)
    matches = mw_data.get("matches", [])
    if not matches:
        st.info(f"第 {selected_week} 節の試合が見つかりません。")
        return

    # Render matches in 2 columns
    c_left, c_right = st.columns(2)
    for i, m in enumerate(matches):
        target_col = c_left if i % 2 == 0 else c_right
        with target_col:
            _render_match_card(m)


def _render_team_report_mini_card(
    card: Dict[str, Any],
    show_rank_number: bool = False,
) -> None:
    """Render a compact report card for a single team in the matchweek."""
    tid = card.get("team_id", "")
    tname = card.get("team_name", tid)
    rank = card.get("rank", "B+")
    score = card.get("total_score", 0)
    critique = card.get("critique", {})
    score_str = card.get("score", "")
    opp_name = card.get("opp_team_name", "")
    mid = card.get("match_id", "")
    metrics = card.get("metrics", {})
    week_rank = card.get("week_rank", 1)

    with st.container(border=True):
        col_rank, col_emb, col_info = st.columns([1, 1, 4])
        with col_rank:
            if show_rank_number:
                medal = (
                    "🥇"
                    if week_rank == 1
                    else ("🥈" if week_rank == 2 else ("🥉" if week_rank == 3 else f"#{week_rank}"))
                )
                st.markdown(f"### {medal}")
            else:
                st.markdown(f"**{card.get('score', '')}**")
        with col_emb:
            st.markdown(
                f"<div style='text-align: center; padding-top: 4px;'>"
                f"{get_team_emblem_html(tid, width=36, height=36)}"
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_info:
            st.markdown(f"**{tname}**")
            st.caption(f"vs {opp_name} ({score_str})")

        # Rank and Score Row
        c_badge, c_pts = st.columns([3, 2])
        with c_badge:
            st.markdown(_get_rank_badge_html(rank), unsafe_allow_html=True)
        with c_pts:
            st.markdown(
                f"<div style='text-align: right;'>"
                f"<b>{score}</b> <span style='font-size:0.8rem;color:#94a3b8;'>/ 60点</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Headline & Text
        st.markdown(
            f"<p style='font-size:0.9rem; margin-top:8px; margin-bottom:4px; font-weight:700;'>"
            f"{critique.get('headline', '')}</p>",
            unsafe_allow_html=True,
        )
        st.caption(critique.get("text", ""))

        # 6-Metric Mini Progress
        metric_keys = [
            ("game_dominance", "支配"),
            ("individual_power", "個"),
            ("style_execution", "型"),
            ("duels_intensity", "球際"),
            ("team_cohesion", "連係"),
            ("excitement_index", "熱"),
        ]
        cols = st.columns(6)
        for i, (m_key, m_label) in enumerate(metric_keys):
            with cols[i]:
                m_score = metrics.get(m_key, {}).get("score", 0)
                st.caption(f"{m_label}:{m_score}")

        if st.button("試合詳細へ ❯", key=f"btn_rc_goto_{mid}_{tid}", use_container_width=True):
            navigate_to(view=VIEW_MATCH, match_id=mid)


def _render_match_pair_report_card(pair: Dict[str, Any]) -> None:
    """Render paired match comparison card with home and away team report cards."""
    mid = pair.get("match_id", "")
    date = pair.get("date", "")
    stadium = pair.get("stadium", "")
    home = pair.get("home", {})
    away = pair.get("away", {})

    with st.container(border=True):
        st.caption(f"📅 {date} | 🏟️ {stadium}")
        c_h, c_vs, c_a = st.columns([5, 1, 5])
        with c_h:
            _render_team_report_mini_card(home, show_rank_number=False)
        with c_vs:
            st.markdown(
                "<div style='text-align:center; padding-top:40px; font-weight:bold; color:#94a3b8;'>VS</div>",
                unsafe_allow_html=True,
            )
        with c_a:
            _render_team_report_mini_card(away, show_rank_number=False)


def _render_matchweek_report_cards_section(
    season: int,
    qa_engine: TacticalQAEngine,
) -> None:
    """Section 3: Matchweek Report Cards for all 20 clubs (エル・ゴラッソ公認 番記者通信簿)."""
    col_title, col_ai = st.columns([3, 1])
    with col_title:
        st.subheader("📰 3. 節別 J1番記者通信簿（全10試合・20チーム一覧）")
        st.caption(
            "当節開催された全10試合・20クラブの6大観点評価（S〜Dランク・合計得点・番記者寸評）を一覧比較できます。"
        )
    with col_ai:
        render_ai_button(
            button_key="ai_btn_mw_report_cards",
            view_type=VIEW_LEAGUE,
            qa_engine=qa_engine,
            section_key="report_cards",
            note=f"{season}シーズン 当節の全チーム通信簿・評価ランキングについて質問",
            button_label="🤖 節の通信簿をAI分析",
        )

    # Available matchweeks
    meta_info = _load_matchweek_data(season=season, matchweek=None)
    available_weeks = meta_info.get("available_matchweeks", [])
    if not available_weeks:
        st.info("日程データが登録されていません。")
        return

    default_week = meta_info.get("selected_matchweek", available_weeks[0])
    selected_week = st.selectbox(
        "通信簿を表示する節を選択",
        options=available_weeks,
        index=available_weeks.index(default_week) if default_week in available_weeks else 0,
        format_func=lambda w: f"第 {w} 節 通信簿",
        key=f"sb_mw_rc_selector_{season}",
    )

    rc_data = _load_matchweek_report_cards(season=season, matchweek=selected_week)
    team_cards = rc_data.get("team_cards", [])
    match_pairs = rc_data.get("match_pairs", [])

    if not team_cards:
        st.info(f"第 {selected_week} 節の完了試合通信簿データがありません。")
        return

    # View Tabs: Ranking vs Pair
    tab_rank, tab_pair = st.tabs([
        "🏆 今節チーム評価ランキング (1位〜20位)",
        "⚔️ 対戦カード別 20チーム対比 (全10試合)",
    ])

    with tab_rank:
        st.caption(f"第 {selected_week} 節の全20チームをエル・ゴラッソ番記者評価得点（60点満点）順に掲載しています。")
        c1, c2 = st.columns(2)
        for idx, card in enumerate(team_cards):
            target_col = c1 if idx % 2 == 0 else c2
            with target_col:
                _render_team_report_mini_card(card, show_rank_number=True)

    with tab_pair:
        st.caption(f"第 {selected_week} 節の全10試合におけるホーム vs アウェイ両軍の通信簿対比です。")
        for pair in match_pairs:
            _render_match_pair_report_card(pair)


def _render_stats_rankings_section(
    season: int,
    qa_engine: TacticalQAEngine,
) -> None:
    """Section 4: League Statistical Rankings (Team & Player Top 5)."""
    col_title, col_ai = st.columns([3, 1])
    with col_title:
        st.subheader("🏅 4. リーグスタッツランキング (Top 5)")
        st.caption("チームおよび選手の主要戦術指標リーダーボードです。選手名から選手名鑑へ直接ジャンプできます。")
    with col_ai:
        render_ai_button(
            button_key="ai_btn_rankings",
            view_type=VIEW_LEAGUE,
            qa_engine=qa_engine,
            section_key="rankings",
            note="リーグスタッツランキング（得点・CBP・走行量など）について分析",
            button_label="🤖 スタッツをAI分析",
        )

    rankings_data = _load_rankings_data(season=season)
    team_rk = rankings_data.get("team_rankings", {})
    player_rk = rankings_data.get("player_rankings", {})

    tab_team, tab_player = st.tabs(["🛡️ チーム部門ランキング", "👤 個人部門ランキング"])

    with tab_team:
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown("##### ⏱️ 平均ボール保持率 (%)")
            for item in team_rk.get("possession", []):
                st.markdown(f"**{item['rank']}. {item['team_name']}** — `{item['value']}%`")

            st.markdown("##### ⚡ チャンス構築率 (%)")
            for item in team_rk.get("chance_create", []):
                st.markdown(f"**{item['rank']}. {item['team_name']}** — `{item['value']}%`")

        with col_t2:
            st.markdown("##### 🏃 平均総走行距離 (km/試合)")
            for item in team_rk.get("distance", []):
                st.markdown(f"**{item['rank']}. {item['team_name']}** — `{item['value']} km`")

            st.markdown("##### 💨 平均スプリント回数 (回/試合)")
            for item in team_rk.get("sprints", []):
                st.markdown(f"**{item['rank']}. {item['team_name']}** — `{item['value']} 回`")

    with tab_player:
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.markdown("##### ⚽ 得点ランキング")
            for p in player_rk.get("goals", []):
                cp_name, cp_btn = st.columns([3, 1])
                with cp_name:
                    st.markdown(f"**{p['rank']}. {p['player_name']}** ({p['team_name']}) — **{p['value']}** 得点")
                with cp_btn:
                    if p.get("player_id") and st.button("詳細", key=f"btn_p_goal_{p['player_id']}_{p['rank']}"):
                        navigate_to(view=VIEW_PLAYER, player_id=p["player_id"], player_name=p["player_name"])

            st.markdown("##### 🎯 アシストランキング")
            for p in player_rk.get("assists", []):
                cp_name, cp_btn = st.columns([3, 1])
                with cp_name:
                    st.markdown(f"**{p['rank']}. {p['player_name']}** ({p['team_name']}) — **{p['value']}** アシスト")
                with cp_btn:
                    if p.get("player_id") and st.button("詳細", key=f"btn_p_ast_{p['player_id']}_{p['rank']}"):
                        navigate_to(view=VIEW_PLAYER, player_id=p["player_id"], player_name=p["player_name"])

        with col_p2:
            st.markdown("##### 🌟 CBP（チャンスビルディング）総合リーダー")
            for p in player_rk.get("cbp_total", []):
                cp_name, cp_btn = st.columns([3, 1])
                with cp_name:
                    st.markdown(f"**{p['rank']}. {p['player_name']}** ({p['team_name']}) — **{p['value']}** pt")
                with cp_btn:
                    if p.get("player_id") and st.button("詳細", key=f"btn_p_cbp_{p['player_id']}_{p['rank']}"):
                        navigate_to(view=VIEW_PLAYER, player_id=p["player_id"], player_name=p["player_name"])

            st.markdown("##### 💨 スプリント回数リーダー")
            for p in player_rk.get("sprints", []):
                cp_name, cp_btn = st.columns([3, 1])
                with cp_name:
                    st.markdown(f"**{p['rank']}. {p['player_name']}** ({p['team_name']}) — **{p['value']}** 回")
                with cp_btn:
                    if p.get("player_id") and st.button("詳細", key=f"btn_p_sp_{p['player_id']}_{p['rank']}"):
                        navigate_to(view=VIEW_PLAYER, player_id=p["player_id"], player_name=p["player_name"])


def _render_tactical_map_section(
    season: int,
    qa_engine: TacticalQAEngine,
) -> None:
    """Section 5: 4-Quadrant Tactical Positioning Map with Plotly."""
    col_title, col_ai = st.columns([3, 1])
    with col_title:
        st.subheader("🗺️ 5. 戦術ポジショニング比較マップ")
        st.caption("20クラブの戦術スタイルや攻守期待値、フィジカル走量を4象限散布図でインタラクティブに比較します。")
    with col_ai:
        render_ai_button(
            button_key="ai_btn_tactical_map",
            view_type=VIEW_LEAGUE,
            qa_engine=qa_engine,
            section_key="tactical_map",
            note="Jリーグ戦術ポジショニング比較マップ（4象限スタイル分布）について分析",
            button_label="🤖 戦術マップをAI分析",
        )

    # Preset selection
    preset_options = {
        "possession_vs_press": "🎯 戦術スタイル (ボール保持率 × プレッシング奪取)",
        "xg_attack_vs_defense": "⚔️ 攻守期待値 (攻撃xG × 守備被xGA)",
        "physical_distance_vs_sprints": "⚡ フィジカル強度 (総走行距離 × スプリント数)",
    }
    selected_preset = st.radio(
        "比較軸プリセットを選択:",
        options=list(preset_options.keys()),
        format_func=lambda k: preset_options[k],
        horizontal=True,
        key=f"radio_tactical_preset_{season}",
    )

    map_data = _load_tactical_map_data(season=season, metric_preset=selected_preset)
    teams = map_data.get("teams", [])
    if not teams:
        st.info("戦術マップデータが見つかりません。")
        return

    x_avg = map_data.get("x_avg", 50.0)
    y_avg = map_data.get("y_avg", 10.0)
    x_label = map_data.get("x_label", "X軸")
    y_label = map_data.get("y_label", "Y軸")
    qlabels = map_data.get("quadrant_labels", {})

    # Calculate data bounds for sizing emblem markers
    x_min = min(t["x"] for t in teams)
    x_max = max(t["x"] for t in teams)
    y_min = min(t["y"] for t in teams)
    y_max = max(t["y"] for t in teams)
    x_range = x_max - x_min if x_max > x_min else 10.0
    y_range = y_max - y_min if y_max > y_min else 10.0
    sizex = x_range * 0.082
    sizey = y_range * 0.082

    # Create Plotly figure
    fig = go.Figure()

    # Add official club emblems as scatter layout images
    for t in teams:
        tid = t.get("team_id", "")
        emb_url = get_team_emblem_url(tid, prefer_png=True)
        if emb_url:
            fig.add_layout_image(
                dict(
                    source=emb_url,
                    xref="x",
                    yref="y",
                    x=t["x"],
                    y=t["y"],
                    sizex=sizex,
                    sizey=sizey,
                    sizing="contain",
                    xanchor="center",
                    yanchor="middle",
                    layer="above",
                )
            )

    # Scatter points for teams (transparent markers for hover tooltip + short name label)
    fig.add_trace(
        go.Scatter(
            x=[t["x"] for t in teams],
            y=[t["y"] for t in teams],
            mode="markers+text",
            text=[t["short_name"] for t in teams],
            textposition="bottom center",
            marker=dict(
                size=24,
                color="rgba(30, 136, 229, 0.01)",
                line=dict(width=0),
            ),
            textfont=dict(size=11, color="#1e293b", weight="bold"),
            hovertemplate=(
                "<b>%{text}</b> (順位: #%{customdata[0]})<br>"
                + f"{x_label}: %{{x}}<br>"
                + f"{y_label}: %{{y}}<br>"
                + "<extra></extra>"
            ),
            customdata=[[t["rank"]] for t in teams],
        ),
    )

    # Add league average cross-lines
    fig.add_vline(x=x_avg, line_width=1.5, line_dash="dash", line_color="#757575")
    fig.add_hline(y=y_avg, line_width=1.5, line_dash="dash", line_color="#757575")

    # Add Quadrant annotations
    x_min = min(t["x"] for t in teams)
    x_max = max(t["x"] for t in teams)
    y_min = min(t["y"] for t in teams)
    y_max = max(t["y"] for t in teams)

    # Annotate 4 corners
    fig.add_annotation(
        x=x_max,
        y=y_max,
        text=f"【{qlabels.get('top_right', '')}】",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font=dict(size=11, color="#2E7D32"),
    )
    fig.add_annotation(
        x=x_min,
        y=y_max,
        text=f"【{qlabels.get('top_left', '')}】",
        showarrow=False,
        xanchor="left",
        yanchor="top",
        font=dict(size=11, color="#F57C00"),
    )
    fig.add_annotation(
        x=x_max,
        y=y_min,
        text=f"【{qlabels.get('bottom_right', '')}】",
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
        font=dict(size=11, color="#1976D2"),
    )
    fig.add_annotation(
        x=x_min,
        y=y_min,
        text=f"【{qlabels.get('bottom_left', '')}】",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font=dict(size=11, color="#C2185B"),
    )

    fig.update_layout(
        title=f"{map_data.get('title', '戦術比較マップ')} (十字線: リーグ平均値)",
        xaxis_title=x_label,
        yaxis_title=y_label,
        height=540,
        margin=dict(l=40, r=40, t=50, b=40),
        plot_bgcolor="#FAFAFA",
    )

    st.plotly_chart(fig, use_container_width=True)

    # Jump to team profile selector
    st.markdown("##### 🔍 チームを選んで詳細戦術分析へジャンプ")
    col_sel, col_go = st.columns([3, 1])
    with col_sel:
        target_team = st.selectbox(
            "クラブを選択",
            options=teams,
            format_func=lambda t: f"#{t['rank']} {t['team_name']}",
            key=f"sb_map_jump_{season}",
        )
    with col_go:
        st.write("")
        st.write("")
        if target_team and st.button("クラブ詳細 ❯", key=f"btn_jump_from_map_{season}", use_container_width=True):
            navigate_to(view=VIEW_TEAM, team_id=target_team["team_id"])


def render_league_view(qa_engine: TacticalQAEngine) -> None:
    """Render J-League Overview complete view."""
    st.title("🏆 Jリーグ全体 観戦ガイド (League Overview)")
    st.markdown(
        "最新順位表・xPTS期待値から全節の試合カード、チーム/個人スタッツリーダーボード、"
        "および全クラブの4象限戦術ポジショニング比較マップを統合提供します。"
    )

    # Season selector
    seasons = get_available_seasons()
    col_season, col_global_ai = st.columns([1, 3])
    with col_season:
        selected_season = st.selectbox("シーズン", options=seasons, index=0, key="league_view_season_sel")
    with col_global_ai:
        render_ai_button(
            button_key="league_header_ai_btn",
            view_type=VIEW_LEAGUE,
            qa_engine=qa_engine,
            section_key="overview",
            note=f"{selected_season}シーズン Jリーグ全体のトレンドや注目カードについて質問",
            button_label="🤖 リーグ全体についてAIに質問",
        )

    st.divider()

    # Load standings data
    standings = _load_standings_data(season=selected_season)

    # Section 1: Standings cards
    _render_standings_section(season=selected_season, standings=standings, qa_engine=qa_engine)

    st.divider()

    # Section 2: Matchweek schedule and cards
    _render_matchweek_section(season=selected_season, qa_engine=qa_engine)

    st.divider()

    # Section 3: Matchweek Report Cards (20 clubs)
    _render_matchweek_report_cards_section(season=selected_season, qa_engine=qa_engine)

    st.divider()

    # Section 4: League stats rankings
    _render_stats_rankings_section(season=selected_season, qa_engine=qa_engine)

    st.divider()

    # Section 5: 4-Quadrant Tactical Positioning Map
    _render_tactical_map_section(season=selected_season, qa_engine=qa_engine)
