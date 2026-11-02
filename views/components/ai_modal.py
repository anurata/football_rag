"""
views/components/ai_modal.py

Ubiquitous AI Tactical QA Dialog Modal (using st.dialog) backed by SQLite persistence.
Supports context injection, real-time QA generation with Gemini, and conversation continuation.
"""

from typing import Any, Dict, List, Optional
import streamlit as st

from agent.qa_engine import TacticalQAEngine
from pipeline.ai_chat_store import AIChatStore


def get_ai_chat_store() -> AIChatStore:
    """Return a cached or newly initialized AIChatStore instance."""
    if "ai_chat_store" not in st.session_state:
        st.session_state["ai_chat_store"] = AIChatStore()
    return st.session_state["ai_chat_store"]


def build_session_key(
    view_type: str,
    section_key: Optional[str] = None,
    match_id: Optional[str] = None,
    team_id: Optional[str] = None,
    player_id: Optional[str] = None,
) -> str:
    """Generate a deterministic session ID based on location context."""
    parts = [view_type]
    if match_id:
        parts.append(f"m_{match_id}")
    if team_id:
        parts.append(f"t_{team_id}")
    if player_id:
        parts.append(f"p_{player_id}")
    if section_key:
        parts.append(f"s_{section_key}")
    return "_".join(parts)


@st.dialog("🤖 戦術AI対話モーダル", width="large")
def show_ai_qa_modal(
    session_id: str,
    title: str,
    view_type: str,
    section_key: Optional[str],
    context_data: Dict[str, Any],
    qa_engine: TacticalQAEngine,
) -> None:
    """
    Renders ubiquitous modal dialog for tactical Q&A.
    Messages are automatically persisted and resumed from SQLite.
    """
    store = get_ai_chat_store()
    session = store.create_or_get_session(
        session_id=session_id,
        title=title,
        view_type=view_type,
        section_key=section_key,
        context_data=context_data,
    )

    _render_modal_header(session, context_data)
    _render_chat_history(session)
    _render_chat_input_form(store, session_id, context_data, qa_engine)


def _render_modal_header(session: Dict[str, Any], context_data: Dict[str, Any]) -> None:
    """Render metadata and contextual scope badges inside the modal."""
    st.markdown(f"#### 💬 {session.get('title', '戦術対話QA')}")

    badges: List[str] = []
    view = session.get("view_type", "GLOBAL")
    badges.append(f"📍 画面: `{view}`")

    sec = session.get("section_key")
    if sec:
        badges.append(f"📑 セクション: `{sec}`")

    mid = context_data.get("match_id")
    if mid:
        badges.append(f"⚽ 試合ID: `{mid}`")

    tid = context_data.get("team_id")
    if tid:
        badges.append(f"🛡️ チーム: `{tid}`")

    pname = context_data.get("player_name")
    if pname:
        badges.append(f"👤 選手: `{pname}`")

    if badges:
        st.caption(" | ".join(badges))
    st.divider()


def _render_chat_history(session: Dict[str, Any]) -> None:
    """Render prior messages from SQLite in chronological order."""
    messages = session.get("messages", [])
    if not messages:
        st.info("💡 質問を入力して戦術AIアナリストと対話を開始してください。（この画面の文脈が自動適用されます）")
        return

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


def _render_chat_input_form(
    store: AIChatStore,
    session_id: str,
    context_data: Dict[str, Any],
    qa_engine: TacticalQAEngine,
) -> None:
    """Render input form, web search toggle, and handle question answering."""
    with st.container():
        col_inp, col_opt = st.columns([4, 1])
        with col_opt:
            enable_search = st.toggle("🌐 Web検索", value=False, key=f"ai_toggle_{session_id}")

        question = st.chat_input("戦術やデータについて質問を入力...", key=f"ai_input_{session_id}")
        if question and question.strip():
            # 1. Save user question
            store.add_message(
                session_id=session_id,
                role="user",
                content=question.strip(),
            )

            # 2. Update title if it's the first question
            session = store.get_session(session_id)
            if session and len(session.get("messages", [])) <= 1:
                short_title = question.strip()[:24] + ("..." if len(question.strip()) > 24 else "")
                store.update_session_title(session_id, short_title)

            # 3. Call QA Engine
            match_id = context_data.get("match_id")
            with st.spinner("🧠 プロ戦術アナリストが推論中..."):
                enriched_question = _inject_context_prompt(question.strip(), context_data)
                res = qa_engine.ask(
                    question=enriched_question,
                    match_id=match_id,
                    enable_web_search=enable_search,
                )
                answer_text = res.get("answer", "回答を生成できませんでした。")
                metadata = {
                    "web_search_queries": res.get("web_search_queries", []),
                    "grounding_sources": res.get("grounding_sources", []),
                    "model_used": res.get("model_used", ""),
                }
                store.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=answer_text,
                    metadata=metadata,
                )

            # Rerun inside dialog to show latest message
            st.rerun()


def _inject_context_prompt(question: str, context_data: Dict[str, Any]) -> str:
    """Prepend context hints if available (e.g. section, focus metrics)."""
    hints: List[str] = []
    sec = context_data.get("section_key")
    if sec:
        hints.append(f"【注目セクション: {sec}】")
    tid = context_data.get("team_id")
    if tid:
        hints.append(f"【注目チーム: {tid}】")
    pname = context_data.get("player_name")
    if pname:
        hints.append(f"【注目選手: {pname}】")
    note = context_data.get("note")
    if note:
        hints.append(f"【補足文脈: {note}】")

    if hints:
        prefix = " ".join(hints) + "\n"
        return prefix + question
    return question


def render_ai_button(
    button_key: str,
    view_type: str,
    qa_engine: TacticalQAEngine,
    section_key: Optional[str] = None,
    match_id: Optional[str] = None,
    team_id: Optional[str] = None,
    player_id: Optional[str] = None,
    player_name: Optional[str] = None,
    note: Optional[str] = None,
    custom_session_id: Optional[str] = None,
    button_label: str = "🤖 AIに質問",
    help_text: str = "このセクションの文脈を引き継いで戦術AIと対話します",
) -> None:
    """
    Renders a button that opens the ubiquitous AI QA modal for the specific section.
    """
    sid = custom_session_id or build_session_key(
        view_type=view_type,
        section_key=section_key,
        match_id=match_id,
        team_id=team_id,
        player_id=player_id,
    )
    context_data: Dict[str, Any] = {
        "section_key": section_key,
        "match_id": match_id,
        "team_id": team_id,
        "player_id": player_id,
        "player_name": player_name,
        "note": note,
    }

    if st.button(button_label, key=button_key, help=help_text):
        show_ai_qa_modal(
            session_id=sid,
            title=f"{button_label} ({section_key or view_type})",
            view_type=view_type,
            section_key=section_key,
            context_data=context_data,
            qa_engine=qa_engine,
        )


def check_and_trigger_auto_ai_modal(
    qa_engine: TacticalQAEngine,
    current_view: str,
) -> None:
    """
    Check if auto_open_ai_modal flag is set (e.g. following a deep link from AI Chat list)
    and open the resumed modal immediately.
    """
    if not st.session_state.get("auto_open_ai_modal", False):
        return

    # Reset trigger flag to prevent repeated reopening on subsequent interactions
    st.session_state["auto_open_ai_modal"] = False

    resume_id = st.session_state.get("resume_session_id")
    if not resume_id:
        return

    store = get_ai_chat_store()
    session = store.get_session(resume_id)
    if not session:
        return

    show_ai_qa_modal(
        session_id=resume_id,
        title=session.get("title", "戦術対話QA"),
        view_type=session.get("view_type", current_view),
        section_key=session.get("section_key"),
        context_data=session.get("context_data", {}),
        qa_engine=qa_engine,
    )

