"""
J-League Tactical Analysis & Watching Guide RAG Dashboard (app.py).
Streamlit-based interactive web frontend for match selection, stats visualization,
4 watching perspectives, and Gemini AI tactical reasoning.
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


# ==============================================================================
# Database & Engine Helpers
# ==============================================================================

@st.cache_resource
def get_engine(db_path: str = DEFAULT_DB_PATH, chroma_dir: str = DEFAULT_CHROMA_DIR) -> TacticalAnalystEngine:
    """Initialize and cache the reasoning engine and hybrid retriever."""
    sql_tools = TacticalSQLTools(db_path=db_path)
    retriever = TacticalHybridRetriever(db_path=db_path, chroma_dir=chroma_dir)
    return TacticalAnalystEngine(sql_tools=sql_tools, retriever=retriever)


def fetch_available_matchweeks(db_path: str = DEFAULT_DB_PATH) -> List[int]:
    """Retrieve distinct matchweeks available in SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT matchweek FROM matches WHERE matchweek IS NOT NULL ORDER BY matchweek;")
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
# UI Component Helpers
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

    categories = ["シュート数", "枠内シュート", "警告"]
    home_vals = [
        home_stats.get("shots") or 0,
        home_stats.get("shots_on_target") or 0,
        0,
    ]
    away_vals = [
        away_stats.get("shots") or 0,
        away_stats.get("shots_on_target") or 0,
        0,
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
        height=320,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_watching_lenses_cards() -> None:
    """Render the 4 Watching Perspectives as visual tactical cards."""
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; border-left: 4px solid #3b82f6; margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #60a5fa;">🔭 レンズ1: 開始10分の「配置の答え合わせ」</h4>
                <p style="font-size: 0.9em; color: #cbd5e1; margin: 0;">
                    ボール非保持時に相手の誰が誰を捕まえにいくか。噛み合わせのズレ（フリーマン）がどこに生じているかを最初の10分で見極める。
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; border-left: 4px solid #10b981; margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #34d399;">⚡ レンズ2: プレスのスイッチ「トリガー」の瞬間</h4>
                <p style="font-size: 0.9em; color: #cbd5e1; margin: 0;">
                    相手SBへボールが渡った瞬間、あるいは後ろ向きのトラップの瞬間に、誰のダッシュを合図に連動プレスが発動するか。
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; border-left: 4px solid #f59e0b; margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #fbbf24;">⚠️ レンズ3: 劣勢を知らせる「炭鉱のカナリア（先行指標）」</h4>
                <p style="font-size: 0.9em; color: #cbd5e1; margin: 0;">
                    失点する前に、セカンドボール回収率やラインの押し下げ、GKへのバックパス急増など、決壊の予兆を見逃さない。
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div style="background: #1e293b; padding: 16px; border-radius: 8px; border-left: 4px solid #ec4899; margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #f472b6;">♟️ レンズ4: 後半60分の「ベンチのチェス（采配の意図）」</h4>
                <p style="font-size: 0.9em; color: #cbd5e1; margin: 0;">
                    交代で入った選手のプレースタイル（個の突破・運動量・高さ）から、監督が仕掛けた盤面の狙いとリスクを読み解く。
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


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
    st.caption("2層ハイブリッドRAG × 因果推論エージェントによるJ1試合分析ダッシュボード")

    engine = get_engine()

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

    tab_guide, tab_stats, tab_ai, tab_reviews = st.tabs(
        [
            "🔭 4つの観戦レンズ",
            "📊 スタッツ比較",
            "🧠 プロ分析官のAI戦術推論",
            "📝 公式レポート・監督＆選手会見",
        ],
    )

    summary = engine.sql_tools.get_match_summary(match_id) or {}
    home_id = selected_match["home_team_id"]
    away_id = selected_match["away_team_id"]

    # Tab 1: Watching Lenses
    with tab_guide:
        st.subheader("🔭 スタジアムや画面で試合が10倍面白くなる「4つの観戦レンズ」")
        render_watching_lenses_cards()

        st.markdown("---")
        st.subheader("💡 この対戦カード向けの観戦ガイド生成")
        if st.button("🚀 この試合の「4つの観戦レンズ」AIガイドを生成", key="btn_guide"):
            with st.spinner("試合ファクトDBおよび戦術ナレッジを検索して観戦ガイドを推論中..."):
                ctx = engine.build_watching_guide(
                    match_id=match_id,
                    formation_home="4-4-2",
                    formation_away="3-4-2-1",
                )
                if gemini_client.is_available():
                    ai_result = engine.run_analysis(ctx, llm_callable=gemini_client.as_callable())
                    st.markdown(ai_result.get("response", ""))
                else:
                    st.info("APIキーが設定されていないため、注入プロンプトを表示します。")
                    st.code(ctx.get("user_prompt", ""), language="markdown")

    # Tab 2: Stats
    with tab_stats:
        st.subheader("📊 定量スタッツのグラフィカル比較")
        render_stats_chart(summary, home_id, away_id)

        events = summary.get("events", [])
        if events:
            st.markdown("#### ⚽ 得点・重要イベント経過")
            for ev in events:
                minute = ev.get("minute") or "-"
                player = ev.get("player_name") or ev.get("team_id", "-")
                st.markdown(f"- **{minute}'** [{ev.get('team_id')}] **{player}** ({ev.get('event_type')})")

    # Tab 3: Tactical AI Reasoning
    with tab_ai:
        st.subheader("🧠 プロ分析官の深い戦術推論（Why / How / What-if）")
        q_type = st.radio(
            "推論タイプを選択してください:",
            options=[
                "【要因分析 (Why)】特定の現象の真因を消去法で特定",
                "【改善処方箋 (How)】ボトルネックの構造的解決策",
                "【反実仮想 (What-if)】戦術変更シミュレーション",
                "【体質診断 (Game State)】先制・同点・ビハインド時のチームDNA",
            ],
            index=0,
        )

        query_input = st.text_input(
            "分析対象の現象または戦術変更を入力:",
            value="敵陣パス成功率低下" if "Why" in q_type else "SBを内側に絞らせる偽SB化",
        )

        if st.button("⚡ AI推論を実行", key="btn_reasoning"):
            with st.spinner("2層RAGのコンテキストを抽出してGeminiで推論中..."):
                if "Why" in q_type:
                    ctx = engine.build_why_analysis(match_id=match_id, team_id=home_id, phenomenon=query_input)
                elif "How" in q_type:
                    ctx = engine.build_how_analysis(team_id=home_id, bottleneck=query_input)
                elif "What-if" in q_type:
                    ctx = engine.build_what_if_analysis(opponent_team_id=away_id, tactical_change=query_input)
                else:
                    ctx = engine.build_game_state_dna_analysis(team_id=home_id, match_id=match_id)

                if gemini_client.is_available():
                    ai_res = engine.run_analysis(ctx, llm_callable=gemini_client.as_callable())
                    st.markdown("### 📋 AI分析結果")
                    st.markdown(ai_res.get("response", ""))
                else:
                    st.warning("Gemini APIキーが未設定のためプロンプトを表示します。")
                    st.code(ctx.get("user_prompt", ""), language="markdown")

    # Tab 4: Qualitative Reviews
    with tab_reviews:
        st.subheader("📝 公式戦評および監督・選手インタビュー全文")
        reviews = fetch_match_reviews(match_id)
        if not reviews:
            st.info("定性レポートがまだ登録されていません。")
        else:
            for rev in reviews:
                rtype = rev.get("review_type", "")
                title = rev.get("title") or rtype
                speaker = rev.get("speaker_name") or ""
                with st.expander(f"【{rtype}】{title} {f'({speaker})' if speaker else ''}", expanded=(rtype == "OFFICIAL_REPORT")):
                    st.markdown(rev.get("content_text", ""))


if __name__ == "__main__":
    main()
