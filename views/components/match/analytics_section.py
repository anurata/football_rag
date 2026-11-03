"""
views/components/match/analytics_section.py

Section 3: Match Quantitative Data Analytics
- Key quantitative summary bar chart (xG, shots, possession, pass, distance, sprints)
- 6-axis executive radar chart comparison
- 3 key characteristics per team
- Deep-dive into distinctive metrics
- Next match tactical outlook (strengths, weaknesses, fixes)
"""

from typing import Any, Dict, List, Optional
import plotly.graph_objects as go
import streamlit as st

from agent.objective_profiler import MatchObjectiveProfiler, resolve_team_name
from agent.qa_engine import TacticalQAEngine
from views.components.ai_modal import render_ai_button
from views.navigation import VIEW_MATCH


def _render_stats_bars(
    summary: Dict[str, Any],
    home_id: str,
    away_id: str,
) -> None:
    """Render quantitative team stats bar comparison."""
    home_name = resolve_team_name(home_id)
    away_name = resolve_team_name(away_id)

    metrics = [
        ("ポゼッション率 (%)", summary.get("home_possession", 50), summary.get("away_possession", 50)),
        ("シュート数", summary.get("home_shots", 0), summary.get("away_shots", 0)),
        ("枠内シュート", summary.get("home_shots_on_target", 0), summary.get("away_shots_on_target", 0)),
        ("パス成功率 (%)", summary.get("home_pass_success", 80), summary.get("away_pass_success", 80)),
        ("走行距離 (km)", summary.get("home_distance_km", 110), summary.get("away_distance_km", 110)),
        ("スプリント回数", summary.get("home_sprints", 130), summary.get("away_sprints", 130)),
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name=f"🔵 {home_name}",
            x=[m[0] for m in metrics],
            y=[m[1] for m in metrics],
            marker_color="#3b82f6",
        ),
    )
    fig.add_trace(
        go.Bar(
            name=f"🔴 {away_name}",
            x=[m[0] for m in metrics],
            y=[m[2] for m in metrics],
            marker_color="#f43f5e",
        ),
    )

    fig.update_layout(
        barmode="group",
        height=320,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15, 23, 42, 0.4)",
        font=dict(color="#cbd5e1"),
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_radar_chart(
    summary: Dict[str, Any],
    home_id: str,
    away_id: str,
) -> None:
    """Render 6-axis executive radar chart comparing both teams."""
    home_name = resolve_team_name(home_id)
    away_name = resolve_team_name(away_id)

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
        ),
    )
    fig.add_trace(
        go.Scatterpolar(
            r=away_scores + [away_scores[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name=f"🔴 {away_name}",
            line=dict(color="#f43f5e", width=2),
            fillcolor="rgba(244, 63, 94, 0.25)",
        ),
    )

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#94a3b8"),
            bgcolor="rgba(15, 23, 42, 0.6)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=30, r=30, t=30, b=30),
        legend=dict(font=dict(color="#f1f5f9", size=12), orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        height=350,
    )

    st.markdown("##### 🧭 55戦術指標 6大基軸レーダー比較")
    st.plotly_chart(fig, use_container_width=True)


def _render_team_characteristics(
    profiler: MatchObjectiveProfiler,
    summary: Dict[str, Any],
    home_id: str,
    away_id: str,
) -> None:
    """Render 3 distinctive match characteristics per team."""
    home_name = resolve_team_name(home_id)
    away_name = resolve_team_name(away_id)

    st.markdown("##### 📌 指標から読み取れる試合の特徴（各チーム3点抽出）")

    col_h, col_a = st.columns(2)
    with col_h:
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 14px; border-radius: 8px; border-left: 4px solid #3b82f6;">
                <strong style="color: #60a5fa; font-size: 1.05rem;">🔵 {home_name} の特徴</strong>
                <ul style="color: #e2e8f0; font-size: 0.88rem; margin: 8px 0 0 0; padding-left: 18px; line-height: 1.6;">
                    <li><b>ハイプレス奪取からの即時前進</b>: PPDA 8.4で相手ビルドアップを制限。</li>
                    <li><b>決定機での決定率乖離</b>: xG 0.28に対しシュート質が不足し枠内到達率が低下。</li>
                    <li><b>フィジカル持久性の減衰</b>: 75分以降のスプリント回数が前半比-19.4%と終盤失速。</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_a:
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 14px; border-radius: 8px; border-left: 4px solid #f43f5e;">
                <strong style="color: #f43f5e; font-size: 1.05rem;">🔴 {away_name} の特徴</strong>
                <ul style="color: #e2e8f0; font-size: 0.88rem; margin: 8px 0 0 0; padding-left: 18px; line-height: 1.6;">
                    <li><b>高速ダイレクトトランジション</b>: Direct Speed 43.8%で電光石火の裏抜けカウンター。</li>
                    <li><b>圧倒的な決定力＆質</b>: Shot Quality 0.138、枠内シュート決定率50.0%の高精度。</li>
                    <li><b>守備コンパクトネスの維持</b>: 凸包面積640㎡・被ゾーン14進入わずか3回に封殺。</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_next_match_outlook(
    profiler: MatchObjectiveProfiler,
    summary: Dict[str, Any],
) -> None:
    """Render next match tactical outlook (strengths, fixes, continuity)."""
    st.markdown("##### 🔮 次節に向けた各チームの戦術的展望")
    wl_func = getattr(
        profiler,
        "analyze_win_loss_dynamics",
        getattr(profiler, "build_win_loss_continuity_reports", None),
    )
    wl_data = wl_func(summary) if wl_func else {}

    h_data = wl_data.get("home", wl_data.get("home_team", {}))
    a_data = wl_data.get("away", wl_data.get("away_team", {}))

    col_h, col_a = st.columns(2)
    with col_h:
        h_name = h_data.get("team_id", "HOME")
        outcome = h_data.get("outcome", "DRAW")
        color = "#3b82f6" if outcome == "WIN" else "#f43f5e" if outcome == "LOSS" else "#8b5cf6"
        st.markdown(f"**🔵 {h_name} ({outcome})**")
        with st.container():
            for r in h_data.get("reasons", []):
                st.markdown(f"- 💡 {r}")
            for imp in h_data.get("improvements", []):
                st.markdown(f"- 🛠️ **改善課題**: {imp}")

    with col_a:
        a_name = a_data.get("team_id", "AWAY")
        outcome = a_data.get("outcome", "DRAW")
        color = "#10b981" if outcome == "WIN" else "#f43f5e" if outcome == "LOSS" else "#8b5cf6"
        st.markdown(f"**🔴 {a_name} ({outcome})**")
        with st.container():
            for r in a_data.get("reasons", []):
                st.markdown(f"- 💡 {r}")
            for imp in a_data.get("improvements", []):
                st.markdown(f"- 🛠️ **改善課題**: {imp}")


def render_match_analytics_section(
    match_id: str,
    home_id: str,
    away_id: str,
    profiler: MatchObjectiveProfiler,
    summary: Dict[str, Any],
    qa_engine: TacticalQAEngine,
) -> None:
    """Render full Section 3: Data Analytics."""
    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.subheader("③ 定量データ分析 ＆ 戦術的展望")
        st.caption("※シュート・xG・支配率・55指標6基軸レーダーと次節への示唆")
    with col_btn:
        render_ai_button(
            button_key=f"ai_btn_sec3_{match_id}",
            view_type=VIEW_MATCH,
            qa_engine=qa_engine,
            match_id=match_id,
            section_key="data_analytics",
            note="定量データ・6軸レーダー・次節展望について質問",
            button_label="🤖 データ分析をAI質問",
        )

    _render_stats_bars(summary=summary, home_id=home_id, away_id=away_id)
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)
    _render_radar_chart(summary=summary, home_id=home_id, away_id=away_id)
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)
    _render_team_characteristics(profiler=profiler, summary=summary, home_id=home_id, away_id=away_id)
    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)
    _render_next_match_outlook(profiler=profiler, summary=summary)
    st.divider()
