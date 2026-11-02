"""
views/settings_view.py

Application settings view for AI models, API keys, and environment parameters.
Consolidates configuration UI into a dedicated settings page.
"""

from typing import Optional
import os
import streamlit as st

from agent.gemini_client import (
    GeminiTacticalClient,
    DEFAULT_GEMINI_MODEL,
    SUPPORTED_GEMINI_MODELS,
)


def get_default_api_key() -> str:
    """Retrieve default Gemini API key from environment or Streamlit secrets."""
    # 1. Check Streamlit secrets
    try:
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            return str(st.secrets["GEMINI_API_KEY"])
    except Exception:
        pass

    # 2. Check environment variables
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key:
        return env_key

    return ""


def init_settings_state() -> None:
    """Initialize LLM and app configuration keys in session state."""
    if "llm_api_key" not in st.session_state:
        st.session_state["llm_api_key"] = get_default_api_key()

    if "llm_model_name" not in st.session_state:
        st.session_state["llm_model_name"] = DEFAULT_GEMINI_MODEL

    if "llm_mock_mode" not in st.session_state:
        st.session_state["llm_mock_mode"] = False


def get_configured_gemini_client() -> GeminiTacticalClient:
    """
    Build and return a configured GeminiTacticalClient instance
    using settings persisted in st.session_state.
    """
    init_settings_state()

    api_key = st.session_state.get("llm_api_key") or None
    model_name = st.session_state.get("llm_model_name") or DEFAULT_GEMINI_MODEL
    mock_mode = bool(st.session_state.get("llm_mock_mode", False))

    return GeminiTacticalClient(
        api_key=api_key,
        model=model_name,
        mock_mode=mock_mode,
    )


def _render_ai_connection_status(api_key: str, mock_mode: bool) -> None:
    """Display connection status badge and helpful guidance."""
    if mock_mode:
        st.warning(
            "🟡 **モックモード有効**: 外部API通信を行わず、ダミーの戦術推論結果を返します。"
            "（テスト・ローカル検証向け）",
            icon="⚠️",
        )
    elif api_key:
        masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
        st.success(
            f"🟢 **APIキー設定済み**: Gemini APIとの通信が有効です。（Key: `{masked_key}`）",
            icon="✅",
        )
    else:
        st.info(
            "ℹ️ **APIキー未設定**: APIキーを入力するか、Secrets / 環境変数 `GEMINI_API_KEY` を設定してください。"
            "キーがない場合は「検証用モックモード」をONにすることで動作確認できます。",
            icon="🔑",
        )


def _render_model_selection_section() -> None:
    """Render LLM model choices and recommendations."""
    st.subheader("🧠 推論モデル設定")

    current_model = st.session_state.get("llm_model_name", DEFAULT_GEMINI_MODEL)
    default_index = 0
    if current_model in SUPPORTED_GEMINI_MODELS:
        default_index = SUPPORTED_GEMINI_MODELS.index(current_model)

    selected_model = st.selectbox(
        "戦術分析に使用するGeminiモデル",
        options=SUPPORTED_GEMINI_MODELS,
        index=default_index,
        help="高精度な戦術推論にはgemini-3.8-flashまたは2.5-flashを推奨します。",
        key="settings_model_selector",
    )
    st.session_state["llm_model_name"] = selected_model

    st.caption(
        "💡 **モデルの選び方**: 日常的なリアルタイム速報やQAには高速な `gemini-3.8-flash`、"
        "長文の試合総括レポートや多角的因果推論の深掘りには `gemini-2.5-pro` が適しています。"
    )


def _render_api_key_section() -> None:
    """Render API key inputs and mock mode toggle."""
    st.subheader("🔑 Gemini API 認証")

    current_api_key = st.session_state.get("llm_api_key", "")
    new_api_key = st.text_input(
        "Gemini API キー",
        value=current_api_key,
        type="password",
        help="Google AI Studioで取得したAPIキーを入力してください。.env / Secrets の値が自動適用されます。",
        key="settings_api_key_input",
    )
    st.session_state["llm_api_key"] = new_api_key.strip()

    is_mock = st.checkbox(
        "検証用モックモードを有効化 (APIキーなしで全UIをテスト可能)",
        value=st.session_state.get("llm_mock_mode", False),
        key="settings_mock_toggle",
    )
    st.session_state["llm_mock_mode"] = is_mock

    _render_ai_connection_status(
        api_key=st.session_state["llm_api_key"],
        mock_mode=st.session_state["llm_mock_mode"],
    )


def _render_data_pipeline_settings() -> None:
    """Render data pipeline and system maintenance settings info."""
    st.subheader("📦 データ基盤 ＆ システム情報")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**SQLite データベース**")
        st.code("data/football.db", language="text")
    with col2:
        st.markdown("**ChromaDB ベクトルストア**")
        st.code("data/chroma_db", language="text")

    st.caption("試合データや戦術知識の更新は、バッチスクリプト (`scripts/update_matchweek.py`) を通じて行われます。")


def render_settings_view() -> None:
    """Render the main Settings view page."""
    init_settings_state()

    st.title("⚙️ システム設定 (Settings)")
    st.markdown(
        "Gemini AIの接続情報、推論モデルの選択、およびデータ基盤の設定を管理します。\n"
        "ここで行った設定変更は、試合詳細やAI対話などすべての画面へ即座に反映されます。"
    )
    st.divider()

    _render_api_key_section()
    st.divider()

    _render_model_selection_section()
    st.divider()

    _render_data_pipeline_settings()
