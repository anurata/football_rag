"""
Gemini API Tactical Analyst Client (agent/gemini_client.py).
Integrates Google GenAI SDK for tactical reasoning and watching guide generation.
"""

import os
from typing import Optional, Dict, Any, Callable, List
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
        enable_google_search: bool = False,
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

        res = self._call_model_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            enable_google_search=enable_google_search,
        )
        return res

    def generate_qa(
        self,
        system_prompt: str,
        user_prompt: str,
        enable_google_search: bool = False,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Generate QA response including Web search grounding sources."""
        if self.mock_mode:
            return self._generate_mock_qa_response(
                user_prompt=user_prompt,
                enable_google_search=enable_google_search,
            )

        if not self.api_key:
            return {
                "text": "【エラー: Gemini APIキーが未設定です】",
                "web_search_queries": [],
                "grounding_sources": [],
                "model_used": "none",
            }

        if not HAS_GENAI_SDK or self._client is None:
            return {
                "text": "【エラー: google-genai パッケージが読み込めませんでした】",
                "web_search_queries": [],
                "grounding_sources": [],
                "model_used": "none",
            }

        return self._call_model_qa_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            enable_google_search=enable_google_search,
        )

    def _call_model_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        enable_google_search: bool = False,
    ) -> str:
        """Try primary model first, fallback to stable models on failure."""
        qa_res = self._call_model_qa_with_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            enable_google_search=enable_google_search,
        )
        return qa_res.get("text", "")

    def _build_config(
        self,
        system_prompt: str,
        temperature: float,
        enable_google_search: bool = False,
    ) -> Any:
        """Helper to create GenerateContentConfig with optional Google Search tool."""
        tools = []
        if enable_google_search:
            tools.append(types.Tool(google_search=types.GoogleSearch()))

        return types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            tools=tools if tools else None,
        )

    def _extract_grounding_metadata(self, response: Any) -> Dict[str, Any]:
        """Extract web search queries and source URLs from response metadata."""
        queries: List[str] = []
        sources: List[Dict[str, str]] = []

        try:
            if not hasattr(response, "candidates") or not response.candidates:
                return {"web_search_queries": queries, "grounding_sources": sources,}

            candidate = response.candidates[0]
            g_meta = getattr(candidate, "grounding_metadata", None)
            if not g_meta:
                return {"web_search_queries": queries, "grounding_sources": sources,}

            # Extract search queries
            raw_queries = getattr(g_meta, "web_search_queries", None)
            if raw_queries:
                queries.extend([str(q) for q in raw_queries if q])

            # Extract grounding chunks (sources)
            chunks = getattr(g_meta, "grounding_chunks", None)
            if chunks:
                for c in chunks:
                    web = getattr(c, "web", None)
                    if web:
                        uri = getattr(web, "uri", "")
                        title = getattr(web, "title", "")
                        if uri:
                            sources.append({
                                "title": title or uri,
                                "url": uri,
                            })
        except Exception:
            pass

        return {
            "web_search_queries": queries,
            "grounding_sources": sources,
        }

    def _call_model_qa_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        enable_google_search: bool = False,
    ) -> Dict[str, Any]:
        """Execute content generation and return text with metadata."""
        candidate_models = [self.model]
        for fb in FALLBACK_GEMINI_MODELS:
            if fb not in candidate_models:
                candidate_models.append(fb)

        last_error = None
        for m in candidate_models:
            try:
                config = self._build_config(
                    system_prompt=system_prompt,
                    temperature=temperature,
                    enable_google_search=enable_google_search,
                )
                response = self._client.models.generate_content(
                    model=m,
                    contents=user_prompt,
                    config=config,
                )
                if response and response.text:
                    meta = self._extract_grounding_metadata(response)
                    return {
                        "text": response.text,
                        "web_search_queries": meta.get("web_search_queries", []),
                        "grounding_sources": meta.get("grounding_sources", []),
                        "model_used": m,
                    }
            except Exception as e:
                last_error = e
                continue

        return {
            "text": f"【Gemini API 呼び出しエラー】: {last_error}",
            "web_search_queries": [],
            "grounding_sources": [],
            "model_used": "error",
        }

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

    def _generate_mock_qa_response(
        self,
        user_prompt: str,
        enable_google_search: bool = False,
    ) -> Dict[str, Any]:
        """Fallback mock QA response for unit testing and offline demo."""
        text = (
            f"### 【QA回答（モック）】\n\n"
            f"ご質問「{user_prompt[:50]}...」について、蓄積された戦術データおよび前提条件から回答します。\n\n"
            f"- **戦術的分析**: 前半のポゼッション時におけるライン間侵入がキーとなっており、相手守備ブロックのズレを突く動きが有効でした。\n"
            f"- **外部コンテキスト**: 中3日の過密日程および累積警告のリスク管理が交代タイミングに影響を与えています。\n"
        )
        sources: List[Dict[str, str]] = []
        queries: List[str] = []

        if enable_google_search:
            text += "\n*※Google検索グラウンディングにより最新の公式情報を補完確認済み*"
            queries.append(f"{user_prompt[:20]} 最新情報")
            sources.append({
                "title": "Jリーグ公式 最新ニュース",
                "url": "https://www.jleague.jp/news/",
            })

        return {
            "text": text,
            "web_search_queries": queries,
            "grounding_sources": sources,
            "model_used": "mock-gemini-flash",
        }

    def as_callable(self) -> Callable[[str, str], str]:
        """Return a callable (system_prompt, user_prompt) -> response_text for engine integration."""
        return lambda sys_p, usr_p: self.generate(sys_p, usr_p)

