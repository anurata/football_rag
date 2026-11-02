"""
views/ai_chat_view.py

Dedicated view for cross-sectional AI tactical conversations and history management.
Allows global Q&A and jumping back to source pages to resume dialogs in-situ.
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from agent.qa_engine import TacticalQAEngine
from pipeline.ai_chat_store import AIChatStore
from views.components.ai_modal import get_ai_chat_store
from views.navigation import (
    VIEW_LEAGUE,
    VIEW_TEAM,
    VIEW_MATCH,
    VIEW_PLAYER,
    navigate_to,
)


def render_ai_chat_view(qa_engine: TacticalQAEngine) -> None:
    """Render the AI Chat History & Cross-Sectional QA page."""
    st.title("🤖 AI対話一覧 ＆ 横断戦術QA")
    st.markdown(
        "観戦ガイドの各セクションでAIと交わした対話履歴をサーバー上で一元管理しています。\n"
        "過去の対話の**「元ページへジャンプ」**を押すと、該当ページへ移動してその箇所の対話をそのまま継続できます。\n"
        "また、ページ上部では試合やクラブを限定しない**横断的な戦術QA**も可能です。"
    )
    st.divider()

    store = get_ai_chat_store()

    tab_global_qa, tab_history = st.tabs(
        [
            "🌐 横断的戦術QA (全体ディスカッション)",
            "📋 過去のAI対話一覧 (履歴・再開)",
        ],
    )

    with tab_global_qa:
        _render_global_qa_section(store, qa_engine)

    with tab_history:
        _render_history_list_section(store)


def _render_global_qa_section(store: AIChatStore, qa_engine: TacticalQAEngine) -> None:
    """Render free-form global Q&A session."""
    st.subheader("🌐 Jリーグ全体・横断戦術ディスカッション")
    st.caption("シーズン全体の戦術トレンド、複数クラブの比較、戦術用語の解説など自由に質問できます。")

    global_session_id = "GLOBAL_TACTICAL_QA"
    session = store.create_or_get_session(
        session_id=global_session_id,
        title="Jリーグ全体・横断戦術QA",
        view_type="GLOBAL",
        section_key="cross_cutting",
        context_data={"note": "全体横断ディスカッション"},
    )

    # Display history
    messages = session.get("messages", [])
    if messages:
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            with st.chat_message(role):
                st.markdown(content)
                meta = msg.get("metadata", {})
                sources = meta.get("grounding_sources", [])
                if sources:
                    with st.expander("🌐 参照ソース・Web検索結果", expanded=False):
                        for src in sources:
                            title = src.get("title", "参照リンク")
                            url = src.get("url", "#")
                            st.markdown(f"- [{title}]({url})")
    else:
        st.info("💡 質問を入力すると、Gemini AIプロ分析官が横断的に推論・回答します。")

    # Form
    col_inp, col_opt = st.columns([4, 1])
    with col_opt:
        enable_search = st.toggle("🌐 Web検索", value=False, key="global_qa_web_toggle")

    user_query = st.chat_input("横断的な戦術質問を入力...", key="global_qa_input")
    if user_query and user_query.strip():
        store.add_message(
            session_id=global_session_id,
            role="user",
            content=user_query.strip(),
        )

        with st.spinner("🧠 全体戦術データを分析・推論中..."):
            res = qa_engine.ask(
                question=user_query.strip(),
                match_id=None,
                enable_web_search=enable_search,
            )
            answer_text = res.get("answer", "回答を生成できませんでした。")
            metadata = {
                "web_search_queries": res.get("web_search_queries", []),
                "grounding_sources": res.get("grounding_sources", []),
                "model_used": res.get("model_used", ""),
            }
            store.add_message(
                session_id=global_session_id,
                role="assistant",
                content=answer_text,
                metadata=metadata,
            )
        st.rerun()


def _render_history_list_section(store: AIChatStore) -> None:
    """Render list of past sessions with jump-to-source-page buttons."""
    st.subheader("📋 蓄積されたAI対話履歴")

    col_filter, col_refresh = st.columns([3, 1])
    with col_filter:
        filter_type = st.selectbox(
            "絞り込み (画面タイプ)",
            options=["すべて", "⚽ 試合 (MATCH)", "🛡️ チーム (TEAM)", "🏆 全体 (LEAGUE)", "👤 選手 (PLAYER)", "🌐 横断 (GLOBAL)"],
            index=0,
            key="history_filter_type",
        )
    with col_refresh:
        if st.button("🔄 最新に更新", key="refresh_history_btn"):
            st.rerun()

    type_mapping = {
        "⚽ 試合 (MATCH)": VIEW_MATCH,
        "🛡️ チーム (TEAM)": VIEW_TEAM,
        "🏆 全体 (LEAGUE)": VIEW_LEAGUE,
        "👤 選手 (PLAYER)": VIEW_PLAYER,
        "🌐 横断 (GLOBAL)": "GLOBAL",
    }
    view_filter = type_mapping.get(filter_type)

    sessions = store.list_sessions(view_type=view_filter, limit=100)
    if not sessions:
        st.info("登録されたAI対話履歴はまだありません。各画面の「🤖 AIに質問」から対話を行ってください。")
        return

    st.write(f"合計 **{len(sessions)}** 件の対話スレッドが見つかりました。")

    for s in sessions:
        _render_session_card(s, store)


def _render_session_card(session: Dict[str, Any], store: AIChatStore) -> None:
    """Render a single session item card with resume deep-link button."""
    sid = session.get("session_id", "")
    title = session.get("title", "対話スレッド")
    view = session.get("view_type", "GLOBAL")
    sec = session.get("section_key") or "general"
    updated = session.get("updated_at", "")[:19].replace("T", " ")
    msg_count = session.get("message_count", 0)
    last_msg = session.get("last_message", "")
    ctx = session.get("context_data", {})

    with st.container(border=True):
        col_main, col_action = st.columns([3, 1])

        with col_main:
            st.markdown(f"**💬 {title}**")
            badge_text = f"`{view}` / `{sec}`"
            if ctx.get("match_id"):
                badge_text += f" | ⚽ 試合: `{ctx.get('match_id')}`"
            if ctx.get("team_id"):
                badge_text += f" | 🛡️ チーム: `{ctx.get('team_id')}`"
            if ctx.get("player_name"):
                badge_text += f" | 👤 選手: `{ctx.get('player_name')}`"

            st.caption(f"{badge_text} | 🕒 最終更新: {updated} | ✉️ {msg_count}件")
            if last_msg:
                preview = (last_msg[:90] + "...") if len(last_msg) > 90 else last_msg
                st.markdown(f"> *{preview}*")

        with col_action:
            if view != "GLOBAL":
                if st.button("🔗 元ページへジャンプ", key=f"jump_{sid}", help="元のページへ移動し、この対話モーダルを自動展開します"):
                    navigate_to(
                        view=view,
                        match_id=ctx.get("match_id"),
                        team_id=ctx.get("team_id"),
                        player_id=ctx.get("player_id"),
                        player_name=ctx.get("player_name"),
                        section_key=sec,
                        resume_session_id=sid,
                        auto_open_ai=True,
                    )
            if st.button("🗑️ 削除", key=f"del_{sid}", help="この対話履歴をサーバーから削除します"):
                store.delete_session(sid)
                st.rerun()

