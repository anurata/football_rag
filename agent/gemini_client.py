"""
Gemini API Tactical Analyst Client (agent/gemini_client.py).
Integrates Google GenAI SDK for tactical reasoning and watching guide generation.
"""

import os
from typing import Optional, Dict, Any, Callable
from pathlib import Path

# Try loading .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False


DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_GEMINI_MODELS = ["gemini-3.5-flash", "gemini-3.1-pro-preview"]
SUPPORTED_GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.8-pro",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]


class GeminiTacticalClient:
    """Client for generating tactical analysis using Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        mock_mode: bool = False,
    ):
        self.mock_mode = mock_mode
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

        self._client = None
        if not self.mock_mode and self.api_key and HAS_GENAI_SDK:
            self._client = genai.Client(api_key=self.api_key)

    def is_available(self) -> bool:
        """Check if client is configured with a valid API key."""
        if self.mock_mode:
            return True
        return bool(self.api_key and HAS_GENAI_SDK and self._client is not None)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        """Generate tactical analysis response from Gemini API."""
        if self.mock_mode:
            return self._generate_mock_response(user_prompt)

        if not self.api_key:
            return (
                "【エラー: Gemini APIキーが未設定です】\n"
                "環境変数 GEMINI_API_KEY を設定するか、プロジェクトルートの .env ファイルに\n"
                "GEMINI_API_KEY=your_api_key_here を記載してください。"
            )

        if not HAS_GENAI_SDK or self._client is None:
            return "【エラー: google-genai パッケージが読み込めませんでした】"

        return self._call_model_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )

    def _call_model_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        """Try primary model first, fallback to stable models on failure."""
        candidate_models = [self.model]
        for fb in FALLBACK_GEMINI_MODELS:
            if fb not in candidate_models:
                candidate_models.append(fb)

        last_error = None
        for m in candidate_models:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                )
                response = self._client.models.generate_content(
                    model=m,
                    contents=user_prompt,
                    config=config,
                )
                if response.text:
                    return response.text
            except Exception as e:
                last_error = e
                continue

        return f"【Gemini API 呼び出しエラー】: {last_error}"

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Any,
        temperature: float = 0.1,
    ) -> Optional[str]:
        """Generate structured JSON conforming to the given schema."""
        if self.mock_mode:
            return None

        if not self.api_key or not HAS_GENAI_SDK or self._client is None:
            return None

        candidate_models = [self.model]
        for fb in FALLBACK_GEMINI_MODELS:
            if fb not in candidate_models:
                candidate_models.append(fb)

        for m in candidate_models:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                )
                response = self._client.models.generate_content(
                    model=m,
                    contents=user_prompt,
                    config=config,
                )
                if response.text:
                    return response.text
            except Exception:
                continue

        return None

    def _generate_mock_response(self, user_prompt: str) -> str:
        """Fallback mock generator for unit tests and offline demonstrations."""
        return (
            "### 【プロ分析官の戦術推論レポート（検証用モック）】\n\n"
            "#### 1. 現象の因果特定（Why）\n"
            "- 定量データおよび監督・選手コメントの照合から、相手のハイプレスによる制限が主因と判定。\n"
            "- ファイナルサード侵入数とハーフスペース利用率の低下が相関。\n\n"
            "#### 2. 戦術的改善処方箋（How）\n"
            "- SBの偽SB化による中央数的優位の形成と、ロングボールのセカンド回収の徹底を推奨。\n\n"
            "#### 3. 次節への観戦レンズ（Watching Perspectives）\n"
            "- 【空間】相手CB-SB間のハーフスペースの攻略速度に注目。\n"
            "- 【時間】後半60分〜75分の選手交代直後のプレス強度の変化を注視。"
        )

    def as_callable(self) -> Callable[[str, str], str]:
        """Return a callable (system_prompt, user_prompt) -> response_text for engine integration."""
        return lambda sys_p, usr_p: self.generate(sys_p, usr_p)

