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

from pipeline.db import DEFAULT_DB_PATH
from pipeline.vector_indexer import DEFAULT_CHROMA_DIR
from agent.sql_tools import TacticalSQLTools
from agent.retriever import TacticalHybridRetriever
from agent.engine import TacticalAnalystEngine
from agent.gemini_client import GeminiTacticalClient, DEFAULT_GEMINI_MODEL
from agent.objective_profiler import MatchObjectiveProfiler
from agent.qualitative_comparator import QualitativeComparator
from agent.player_rater import PlayerRatingGenerator


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
    retriever = TacticalHybridRetriever(db_path=db_path, chroma_dir=chroma_dir)
    return TacticalAnalystEngine(sql_tools=sql_tools, retriever=retriever)


@st.cache_resource
def get_analysis_modules() -> tuple[MatchObjectiveProfiler, QualitativeComparator, PlayerRatingGenerator]:
    """Initialize and cache the objective profiler, qualitative comparator, and player rater."""
    profiler = MatchObjectiveProfiler()
    comparator = QualitativeComparator()
    rater = PlayerRatingGenerator()
    return profiler, comparator, rater


def fetch_available_matchweeks(db_path: str = DEFAULT_DB_PATH) -> List[int]:
    """Retrieve distinct matchweeks available in SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT matchweek FROM matches WHERE matchweek IS NOT NULL ORDER BY matchweek;",
    )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows] if rows else list(range(1, 13))


def fetch_matches_for_mw(mw: int, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve all match cards for a specific matchweek."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
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
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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

def render_header(match: Dict[str, Any]) -> None:
    """Render the top match card header with scores and meta info."""
    home_score = match.get("home_score", "-")
    away_score = match.get("away_score", "-")
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 20px; border-radius: 12px; margin-bottom: 24px; border: 1px solid #334155;">
            <div style="display: flex; justify-content: space-between; align-items: center; text-align: center;">
                <div style="flex: 1;">
                    <h2 style="margin: 0; color: #60a5fa; font-weight: 700;">{match.get('home_team_id', 'HOME')}</h2>
                    <span style="font-size: 0.9em; color: #94a3b8;">ホーム</span>
                </div>
                <div style="flex: 1;">
                    <div style="font-size: 2.8em; font-weight: 900; letter-spacing: 4px; color: #f8fafc;">
                        {home_score} - {away_score}
                    </div>
                    <span style="display: inline-block; background: #3b82f6; color: white; padding: 2px 10px; border-radius: 9999px; font-size: 0.8em; font-weight: 600;">
                        第 {match.get('matchweek', '-')} 節
                    </span>
                </div>
                <div style="flex: 1;">
                    <h2 style="margin: 0; color: #f43f5e; font-weight: 700;">{match.get('away_team_id', 'AWAY')}</h2>
                    <span style="font-size: 0.9em; color: #94a3b8;">アウェイ</span>
                </div>
            </div>
            <div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid #334155; display: flex; justify-content: space-around; color: #cbd5e1; font-size: 0.9em;">
                <span>📅 {match.get('date', '-')}</span>
                <span>🏟️ {match.get('stadium', '-')}</span>
                <span>🌤️ {match.get('weather', '-')}</span>
                <span>👥 {match.get('attendance', 0):,} 人</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stats_chart(summary: Dict[str, Any], home_id: str, away_id: str) -> None:
    """Render a comparative horizontal bar chart of team stats using Plotly."""
    stats_map = summary.get("team_stats", {})
    home_stats = stats_map.get(home_id, {})
    away_stats = stats_map.get(away_id, {})

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
            name=home_id,
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
            name=away_id,
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

def render_objective_perspectives_tab(
    profiler: MatchObjectiveProfiler,
    summary: Dict[str, Any],
) -> None:
    """Render the 15-perspective purely objective analysis and win/loss/improvements."""
    st.subheader("📊 客観データ多角分析（15の観点 ＆ ゲームフロー再構築）")
    st.caption("※監督会見や選手コメント等の定性主観データを完全遮断し、スタッツ・1分攻勢フロー・座標・CBPのみから客観的に導出した事実レポートです。")

    report = profiler.build_15_perspective_report(summary)
    perspectives = report.get("perspectives", [])

    for idx, p in enumerate(perspectives, 1):
        p_name = p.get("name", "")
        layers_str = " | ".join(p.get("applicable_layers", []))
        summary_txt = p.get("summary", "")

        with st.expander(f"【観点 {idx}】{p_name} ［{layers_str}］", expanded=(idx <= 2)):
            st.markdown(f"**💡 サマリー**: {summary_txt}")

            col1, col2 = st.columns([1, 1])
            with col1:
                st.markdown("##### 🔢 【段階1】純粋データ事実")
                data_dict = p.get("layer1_data", {})
                for k, v in data_dict.items():
                    st.markdown(f"- **{k}**: `{v}`")

            with col2:
                st.markdown("##### ⚡ 【段階2】試合速報の重畳")
                st.markdown(f"> {p.get('layer2_events', '該当データなし')}")

                st.markdown("##### 🧠 【段階3】有識者知見からの類推")
                st.markdown(f"> {p.get('layer3_tactics', '該当理論なし')}")

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
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; border-left: 4px solid #3b82f6; margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #60a5fa;">🔵 {home_data.get('team_id', 'HOME')}（勝者側）</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("##### 🏆 【勝因】")
        for r in home_data.get("win_reasons", []):
            st.markdown(f"- {r}")

        st.markdown("##### ⚠️ 【改善点】(大勝の裏の隙)")
        for r in home_data.get("improvements", []):
            st.markdown(f"- {r}")

        st.markdown("##### 🔁 【継続点】(次節も徹底すべき強み)")
        for r in home_data.get("continuity", []):
            st.markdown(f"- {r}")

    with col_a:
        st.markdown(
            f"""
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; border-left: 4px solid #f43f5e; margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #f43f5e;">🔴 {away_data.get('team_id', 'AWAY')}（敗者側）</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("##### 💔 【敗因】")
        for r in away_data.get("loss_reasons", []):
            st.markdown(f"- {r}")

        st.markdown("##### 🛠️ 【改善点】(次節への処方箋)")
        for r in away_data.get("improvements", []):
            st.markdown(f"- {r}")

        st.markdown("##### 🌟 【継続点】(大敗でも評価すべき点)")
        for r in away_data.get("continuity", []):
            st.markdown(f"- {r}")


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

def render_player_ratings_tab(
    rater: PlayerRatingGenerator,
    summary: Dict[str, Any],
) -> None:
    """Render the player ratings, MOM selection, and coach evaluations."""
    st.subheader("🏅 客観データ＆定性統合 選手・監督採点＆寸評")
    st.caption("※10点満点（基準点: 6.0、0.5点刻み）。CBP・スタッツとピッチ上のタスク遂行度を総合評価。")

    ratings = rater.generate_match_ratings(summary)
    mom = ratings.get("mom", {})

    # MOM Banner
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e3a8a, #172554); padding: 18px; border-radius: 10px; border: 2px solid #60a5fa; margin-bottom: 24px;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <span style="background: #fbbf24; color: #000; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 0.85em;">
                        {mom.get('title', 'MOM')}
                    </span>
                    <h3 style="margin: 8px 0 4px 0; color: #ffffff;">{mom.get('player_name')} ({mom.get('team_id')})</h3>
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
        st.markdown("#### 🔵 FC東京 選手採点")
        for p in ratings.get("home_players", []):
            st.markdown(
                f"""
                <div style="background: #1e293b; padding: 10px 14px; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid #3b82f6;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong>#{p.get('number')} {p.get('name')} <span style="color:#94a3b8; font-size:0.85em;">({p.get('position')} / {p.get('minutes')})</span></strong>
                        <span style="background:#3b82f6; color:white; padding:1px 8px; border-radius:4px; font-weight:bold;">{p.get('rating')}</span>
                    </div>
                    <p style="font-size:0.85em; color:#cbd5e1; margin: 4px 0 0 0;">{p.get('comment')}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_a:
        st.markdown("#### 🔴 水戸ホーリーホック 選手採点")
        for p in ratings.get("away_players", []):
            st.markdown(
                f"""
                <div style="background: #1e293b; padding: 10px 14px; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid #f43f5e;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong>#{p.get('number')} {p.get('name')} <span style="color:#94a3b8; font-size:0.85em;">({p.get('position')} / {p.get('minutes')})</span></strong>
                        <span style="background:#f43f5e; color:white; padding:1px 8px; border-radius:4px; font-weight:bold;">{p.get('rating')}</span>
                    </div>
                    <p style="font-size:0.85em; color:#cbd5e1; margin: 4px 0 0 0;">{p.get('comment')}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

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

    st.title("⚽ Jリーグ戦術分析・観戦ガイド RAG システム")
    st.caption("2層ハイブリッドRAG × 客観データ多角分析・定性対比エージェント")

    engine = get_engine()
    profiler, comparator, rater = get_analysis_modules()

    # --------------------------------------------------------------------------
    # Sidebar Filters
    # --------------------------------------------------------------------------
    st.sidebar.header("🔍 試合選択フィルター")

    matchweeks = fetch_available_matchweeks()
    selected_mw = st.sidebar.selectbox("節数を選択", options=matchweeks, index=0)

    matches_in_mw = fetch_matches_for_mw(selected_mw)
    if not matches_in_mw:
        st.sidebar.warning(f"第 {selected_mw} 節の試合データが見つかりませんでした。")
        return

    match_options = {
        f"{m['home_team_id']} {m['home_score']}-{m['away_score']} {m['away_team_id']} ({m['date']})": m
        for m in matches_in_mw
    }
    selected_label = st.sidebar.selectbox("試合カードを選択", options=list(match_options.keys()))
    selected_match = match_options[selected_label]
    match_id = selected_match["match_id"]

    # LLM Settings in Sidebar
    st.sidebar.markdown("---")
    st.sidebar.header("🤖 Gemini AI 設定")
    api_key_input = st.sidebar.text_input(
        "Gemini API キー (未入力時は環境変数を使用)",
        type="password",
        help=".env や環境変数 GEMINI_API_KEY があれば自動適用されます",
    )
    model_name = st.sidebar.selectbox(
        "モデル選択",
        options=["gemini-2.5-flash", "gemini-2.5-pro"],
        index=0,
    )
    use_mock = st.sidebar.checkbox("検証用モックモード (APIキー不要)", value=False)

    gemini_client = GeminiTacticalClient(
        api_key=api_key_input or None,
        model=model_name,
        mock_mode=use_mock,
    )

    # --------------------------------------------------------------------------
    # Main Content Area
    # --------------------------------------------------------------------------
    render_header(selected_match)

    summary = engine.sql_tools.get_match_summary(match_id) or {}
    home_id = selected_match["home_team_id"]
    away_id = selected_match["away_team_id"]
    reviews = fetch_match_reviews(match_id)

    tab_obj, tab_comp, tab_rate, tab_adv, tab_stats, tab_ai, tab_raw = st.tabs(
        [
            "📊 客観データ多角分析 (15観点)",
            "⚖️ 定性対比・答え合わせ",
            "🏅 選手・監督採点＆寸評",
            "🚀 5大発展戦術レポート",
            "📈 スタッツグラフ比較",
            "🧠 プロ分析官のAI深層推論",
            "📝 公式レポート・会見全文",
        ],
    )

    # Tab 1: Objective Analysis
    with tab_obj:
        render_objective_perspectives_tab(profiler, summary)

    # Tab 2: Qualitative Comparison
    with tab_comp:
        render_qualitative_comparison_tab(comparator, profiler, match_id, summary, reviews)

    # Tab 3: Player Ratings
    with tab_rate:
        render_player_ratings_tab(rater, summary)

    # Tab 4: 5 Advanced Reports
    with tab_adv:
        render_advanced_reports_tab(profiler, summary)

    # Tab 5: Stats Chart
    with tab_stats:
        st.subheader("📊 定量スタッツのグラフィカル比較")
        render_stats_chart(summary, home_id, away_id)

    # Tab 6: AI Reasoning
    with tab_ai:
        render_ai_reasoning_tab(engine, gemini_client, match_id, home_id, away_id)

    # Tab 7: Raw Qualitative Reviews
    with tab_raw:
        st.subheader("📝 公式戦評および監督・選手インタビュー全文")
        if not reviews:
            st.info("定性レポートがまだ登録されていません。")
        else:
            for rev in reviews:
                rtype = rev.get("review_type", "")
                title = rev.get("title") or rtype
                speaker = rev.get("speaker_name") or ""
                with st.expander(
                    f"【{rtype}】{title} {f'({speaker})' if speaker else ''}",
                    expanded=(rtype == "OFFICIAL_REPORT"),
                ):
                    st.markdown(rev.get("content_text", ""))


if __name__ == "__main__":
    main()
