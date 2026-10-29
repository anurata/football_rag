"""
YouTube Tactical Knowledge Ingestion Engine (scripts/ingest_youtube_tactics.py).

Features:
1. Multi-channel incremental video discovery (deduped via ingest_history.json).
2. Supports YouTube 2026 lockupViewModel & videoRenderer JSON parsing + channel search.
3. Transcript acquisition with timestamp retention via youtube-transcript-api.
4. Raw data local caching (data/raw/youtube/{video_id}.json).
5. Evidence-backed cumulative updates to knowledge/team_tactical_profiles.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("youtube_tactics_ingester")

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "youtube_tactical_channels.json"
HISTORY_PATH = ROOT_DIR / "data" / "raw" / "youtube" / "ingest_history.json"
RAW_YOUTUBE_DIR = ROOT_DIR / "data" / "raw" / "youtube"
PROFILES_PATH = ROOT_DIR / "knowledge" / "team_tactical_profiles.json"

SYSTEM_UI_LABELS: Set[str] = {
    "キーボード ショートカット",
    "このチャンネルのメンバーになりますか？",
    "再生",
    "ミュート",
}


def ensure_directories() -> None:
    """Ensure required output directories exist."""
    RAW_YOUTUBE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_json_safely(path: Path, default: Any = None) -> Any:
    """Load JSON from path safely, returning default on error."""
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to read JSON from %s: %s", path, e)
        return default


def save_json_safely(path: Path, data: Any) -> None:
    """Save data as pretty JSON with utf-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _extract_from_video_renderer(vr: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Extract (video_id, title) from a YouTube videoRenderer dict."""
    vid = vr.get("videoId", "")
    title_obj = vr.get("title", {})
    runs = title_obj.get("runs", [])
    title = "".join(r.get("text", "") for r in runs).strip()
    if not title:
        title = str(title_obj.get("simpleText", "")).strip()
    if len(vid) == 11 and len(title) > 2 and title not in SYSTEM_UI_LABELS:
        return (vid, title)
    return None


def _extract_from_lockup_view_model(lvm: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Extract (video_id, title) from YouTube's newer lockupViewModel dict."""
    vid = str(lvm.get("contentId", "")).strip()
    meta = lvm.get("metadata", {}).get("lockupMetadataViewModel", {})
    title = str(meta.get("title", {}).get("content", "")).strip()
    if len(vid) == 11 and len(title) > 2 and title not in SYSTEM_UI_LABELS:
        return (vid, title)
    return None


def _walk_yt_initial_data(node: Any, out_list: List[Tuple[str, str]]) -> None:
    """Recursively traverse ytInitialData JSON tree to collect video candidates."""
    if isinstance(node, dict):
        if "videoRenderer" in node and isinstance(node["videoRenderer"], dict):
            pair = _extract_from_video_renderer(node["videoRenderer"])
            if pair:
                out_list.append(pair)
        if "lockupViewModel" in node and isinstance(node["lockupViewModel"], dict):
            pair = _extract_from_lockup_view_model(node["lockupViewModel"])
            if pair:
                out_list.append(pair)
        for val in node.values():
            _walk_yt_initial_data(val, out_list)
    elif isinstance(node, list):
        for item in node:
            _walk_yt_initial_data(item, out_list)


def _extract_candidates_regex_fallback(html: str) -> List[Tuple[str, str]]:
    """Regex-based fallback for mock HTML snippets or legacy markup."""
    candidates: List[Tuple[str, str]] = []
    seen_ids: Set[str] = set()

    pattern_renderer = re.compile(
        r'"videoId":"([a-zA-Z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}\]',
        re.DOTALL,
    )
    for match in pattern_renderer.finditer(html):
        vid, title = match.group(1), match.group(2).strip()
        if (
            vid not in seen_ids
            and len(vid) == 11
            and title not in SYSTEM_UI_LABELS
            and len(title) > 2
        ):
            seen_ids.add(vid)
            candidates.append((vid, title))

    if not candidates:
        simple_pattern = re.compile(r'"videoId":"([a-zA-Z0-9_-]{11})"')
        for match in simple_pattern.finditer(html):
            vid = match.group(1)
            if vid not in seen_ids and len(vid) == 11:
                seen_ids.add(vid)
                candidates.append((vid, "YouTube Video"))

    return candidates


def extract_video_candidates_from_html(html: str) -> List[Tuple[str, str]]:
    """
    Extract (video_id, title) pairs from YouTube channel /videos or /search HTML.
    Uses exact ytInitialData JSON parsing first, falling back to regex for snippets.
    """
    seen_ids: Set[str] = set()
    deduped: List[Tuple[str, str]] = []

    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html)
    if m:
        try:
            data = json.loads(m.group(1))
            raw_pairs: List[Tuple[str, str]] = []
            _walk_yt_initial_data(data, raw_pairs)
            for vid, title in raw_pairs:
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    deduped.append((vid, title))
            if deduped:
                return deduped
        except Exception as e:
            logger.warning("ytInitialData JSON parse failed, using fallback: %s", e)

    return _extract_candidates_regex_fallback(html)


def fetch_channel_html(url: str, timeout: int = 12) -> str:
    """Fetch channel page HTML with custom User-Agent."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


class YouTubeRateLimitError(RuntimeError):
    """Raised when YouTube temporarily blocks transcript fetches due to rate limits."""


def fetch_video_transcript(video_id: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch Japanese or English transcript for video using youtube_transcript_api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        yta = YouTubeTranscriptApi()
        fetched = yta.fetch(video_id, languages=["ja", "en"])
        return [
            {
                "text": item.text,
                "start": item.start,
                "duration": item.duration,
            }
            for item in fetched
        ]
    except Exception as e:
        err_cls = type(e).__name__
        if err_cls in {"IpBlocked", "RequestBlocked"} or "blocking requests" in str(e):
            raise YouTubeRateLimitError(f"Rate limited on {video_id}: {err_cls}") from e
        logger.info("Transcript unavailable for video %s: %s", video_id, e)
        return None


def clean_transcript_text(transcript: List[Dict[str, Any]]) -> str:
    """Combine transcript snippets into single clean text string."""
    return " ".join(
        [
            snippet.get("text", "").strip()
            for snippet in transcript
            if snippet.get("text")
        ],
    )


class YouTubeTacticalIngester:
    """
    Ingests tactical YouTube channels incrementally, fetches transcripts,
    and updates team tactical profiles.
    """

    def __init__(
        self,
        config_path: Path = CONFIG_PATH,
        history_path: Path = HISTORY_PATH,
        raw_dir: Path = RAW_YOUTUBE_DIR,
        profiles_path: Path = PROFILES_PATH,
    ) -> None:
        self.config_path = config_path
        self.history_path = history_path
        self.raw_dir = raw_dir
        self.profiles_path = profiles_path
        ensure_directories()
        self.channels_config: Dict[str, Any] = load_json_safely(
            config_path,
            {"channels": []},
        )
        self.history: Dict[str, Any] = load_json_safely(history_path, {})
        self.profiles_master: Dict[str, Any] = load_json_safely(
            profiles_path,
            {"teams": {}},
        )

    def is_video_processed(self, video_id: str) -> bool:
        """Check if video ID has already been successfully ingested."""
        record = self.history.get(video_id)
        if not record:
            return False
        return record.get("status") in {"SUCCESS", "NO_TRANSCRIPT"}

    def record_history(
        self,
        video_id: str,
        channel_id: str,
        title: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Record video processing status to history file."""
        now_iso = datetime.now(timezone.utc).isoformat()
        self.history[video_id] = {
            "video_id": video_id,
            "channel_id": channel_id,
            "title": title,
            "status": status,
            "error_message": error_message,
            "updated_at": now_iso,
        }
        save_json_safely(self.history_path, self.history)

    def _discover_from_url(self, target_url: str) -> List[Tuple[str, str]]:
        """Fetch target URL and extract candidate (video_id, title) list."""
        try:
            html = fetch_channel_html(target_url)
            return extract_video_candidates_from_html(html)
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", target_url, e)
            return []

    def discover_new_videos(
        self,
        channel_info: Dict[str, Any],
        max_videos: int = 5,
        search_query: str = "FC東京",
    ) -> List[Tuple[str, str]]:
        """
        Discover unprocessed videos according to channel scan_mode:
        - FULL_CHANNEL: Crawl /videos broadly (up to max_videos * 2).
        - SEARCH_AND_RECENT: Crawl channel /search?query=FC東京 first, then /videos.
        """
        raw_url = channel_info.get("url", "").rstrip("/")
        if not raw_url:
            return []

        scan_mode = channel_info.get("scan_mode", "FULL_CHANNEL")
        effective_limit = max_videos * 2 if scan_mode == "FULL_CHANNEL" else max_videos

        combined_candidates: List[Tuple[str, str]] = []
        seen_ids: Set[str] = set()

        if scan_mode == "SEARCH_AND_RECENT" and search_query:
            encoded_q = urllib.parse.quote(search_query)
            search_url = f"{raw_url}/search?query={encoded_q}"
            for vid, title in self._discover_from_url(search_url):
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    combined_candidates.append((vid, title))

        videos_url = f"{raw_url}/videos"
        for vid, title in self._discover_from_url(videos_url):
            if vid not in seen_ids:
                seen_ids.add(vid)
                combined_candidates.append((vid, title))

        new_candidates: List[Tuple[str, str]] = []
        for vid, title in combined_candidates:
            if not self.is_video_processed(vid):
                new_candidates.append((vid, title))
            if len(new_candidates) >= effective_limit:
                break

        return new_candidates

    def extract_tactical_insights_rule_based(
        self,
        transcript_text: str,
        video_title: str,
    ) -> List[Dict[str, Any]]:
        """
        Deterministic rule-based tactical extraction fallback.
        Matches keywords and extracts team/manager tactical mentions.
        """
        insights: List[Dict[str, Any]] = []

        team_keywords: Dict[str, Tuple[str, List[str]]] = {
            "FCT": (
                "FC東京",
                [
                    "松橋",
                    "力蔵",
                    "クラモフスキー",
                    "FC東京",
                    "マルセロ",
                    "ヒアン",
                    "仲川",
                    "俵積田",
                    "バングーナガンデ",
                    "稲村",
                    "ショルツ",
                    "長倉",
                    "安斎",
                ],
            ),
            "ZEL": (
                "FC町田ゼルビア",
                ["黒田剛", "町田ゼルビア", "町田", "ロングスロー", "オセフン", "デューク"],
            ),
            "VOB": (
                "ヴィッセル神戸",
                ["吉田孝行", "ヴィッセル", "神戸", "大迫", "武藤", "セカンドボール"],
            ),
            "MAR": (
                "横浜F・マリノス",
                ["マリノス", "ハイライン", "ハッチンソン", "偽SB", "アタッキング"],
            ),
            "SAN": (
                "京都サンガF.C.",
                ["京都サンガ", "曺貴裁", "ハイプレス", "スプリント"],
            ),
            "MIT": ("水戸ホーリーホック", ["水戸", "森直樹", "ホーリーホック"]),
            "URA": ("浦和レッズ", ["浦和", "スコルジャ", "レッズ"]),
            "KAS": ("鹿島アントラーズ", ["鹿島", "ポポヴィッチ", "アントラーズ"]),
            "GAM": ("ガンバ大阪", ["ガンバ", "ポヤトス"]),
        }

        full_content = f"{video_title} {transcript_text}"

        for team_id, (team_name, keywords) in team_keywords.items():
            matches_found = [kw for kw in keywords if kw in full_content]
            if len(matches_found) >= 2 or (
                len(matches_found) >= 1 and team_name in video_title
            ):
                snippets: List[str] = []
                for kw in matches_found[:2]:
                    pos = transcript_text.find(kw)
                    if pos != -1:
                        start = max(0, pos - 50)
                        end = min(len(transcript_text), pos + 150)
                        snippets.append(transcript_text[start:end].strip())

                insights.append(
                    {
                        "team_id": team_id,
                        "team_name": team_name,
                        "matched_keywords": matches_found,
                        "key_quote": (
                            " ... ".join(snippets)[:300] if snippets else video_title
                        ),
                        "confidence": "HIGH" if len(matches_found) >= 3 else "MEDIUM",
                    },
                )

        return insights

    def merge_evidence_into_profiles(
        self,
        insights: List[Dict[str, Any]],
        video_id: str,
        video_title: str,
        channel_name: str,
    ) -> None:
        """Merge extracted insights into team_tactical_profiles.json idempotently."""
        teams = self.profiles_master.setdefault("teams", {})
        now_iso = datetime.now(timezone.utc).isoformat()

        for ins in insights:
            t_id = ins.get("team_id")
            if not t_id:
                continue

            t_profile = teams.setdefault(
                t_id,
                {
                    "team_id": t_id,
                    "team_name": ins.get("team_name", t_id),
                    "manager": "監督",
                    "base_formation": "4-4-2",
                    "in_possession": {},
                    "out_of_possession": {},
                    "transitions": {},
                    "structural_vulnerabilities": [],
                    "evidences": [],
                },
            )

            evidences: List[Dict[str, Any]] = t_profile.setdefault("evidences", [])
            if not any(ev.get("video_id") == video_id for ev in evidences):
                evidences.append(
                    {
                        "video_id": video_id,
                        "video_title": video_title,
                        "video_url": f"https://www.youtube.com/watch?v={video_id}",
                        "channel_name": channel_name,
                        "key_quote": ins.get("key_quote", ""),
                        "confidence": ins.get("confidence", "MEDIUM"),
                        "ingested_at": now_iso,
                    },
                )

        self.profiles_master["updated_at"] = now_iso
        save_json_safely(self.profiles_path, self.profiles_master)

    def process_single_video(
        self,
        video_id: str,
        video_title: str,
        channel_name: str,
        channel_id: str,
    ) -> bool:
        """Fetch transcript, extract tactical insight, save cache, and update profiles."""
        transcript = fetch_video_transcript(video_id)
        if not transcript:
            self.record_history(
                video_id=video_id,
                channel_id=channel_id,
                title=video_title,
                status="NO_TRANSCRIPT",
                error_message="Transcript not available or disabled",
            )
            return False

        cache_path = self.raw_dir / f"{video_id}.json"
        raw_payload = {
            "video_id": video_id,
            "title": video_title,
            "channel_name": channel_name,
            "channel_id": channel_id,
            "transcript": transcript,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        save_json_safely(cache_path, raw_payload)

        text = clean_transcript_text(transcript)
        insights = self.extract_tactical_insights_rule_based(text, video_title)

        if insights:
            self.merge_evidence_into_profiles(
                insights=insights,
                video_id=video_id,
                video_title=video_title,
                channel_name=channel_name,
            )

        self.record_history(
            video_id=video_id,
            channel_id=channel_id,
            title=video_title,
            status="SUCCESS",
        )
        return True

    def run_incremental_ingest(
        self,
        max_videos_per_channel: int = 4,
        target_channel_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute incremental crawl and ingestion across registered channels."""
        summary = {
            "channels_checked": 0,
            "videos_discovered": 0,
            "transcripts_fetched": 0,
            "transcripts_skipped": 0,
            "errors": 0,
        }

        channels: List[Dict[str, Any]] = self.channels_config.get("channels", [])
        if target_channel_id:
            channels = [c for c in channels if c.get("channel_id") == target_channel_id]

        rate_limited = False
        for ch in channels:
            if rate_limited:
                break
            ch_name = ch.get("name", "Unknown")
            ch_id = ch.get("channel_id", "unknown")
            summary["channels_checked"] += 1

            new_vids = self.discover_new_videos(ch, max_videos=max_videos_per_channel)
            summary["videos_discovered"] += len(new_vids)

            for vid, title in new_vids:
                if self.is_video_processed(vid):
                    summary["transcripts_skipped"] += 1
                    continue

                try:
                    success = self.process_single_video(
                        video_id=vid,
                        video_title=title,
                        channel_name=ch_name,
                        channel_id=ch_id,
                    )
                    time.sleep(1.5)
                except YouTubeRateLimitError as rle:
                    logger.warning("Circuit breaker tripped due to YouTube rate limit: %s", rle)
                    self.record_history(
                        video_id=vid,
                        channel_id=ch_id,
                        title=title,
                        status="RATE_LIMITED",
                        error_message=str(rle),
                    )
                    rate_limited = True
                    break

                if success:
                    summary["transcripts_fetched"] += 1
                else:
                    summary["errors"] += 1

        return summary


def main() -> None:
    """CLI Entrypoint for YouTube tactical ingestion."""
    import sys

    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="YouTube Tactical Knowledge Incremental Ingester",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        default=True,
        help="Run incremental discovery on configured channels",
    )
    parser.add_argument(
        "--max-per-channel",
        type=int,
        default=4,
        help="Base max new videos per channel (doubled for FULL_CHANNEL)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        default=None,
        help="Target single channel_id",
    )
    parser.add_argument(
        "--video-id",
        type=str,
        default=None,
        help="Ingest a specific video ID directly",
    )

    args = parser.parse_args()
    ingester = YouTubeTacticalIngester()

    if args.video_id:
        print(f"Directly ingesting single video ID: {args.video_id}")
        ok = ingester.process_single_video(
            video_id=args.video_id,
            video_title="Manual Direct Ingestion",
            channel_name="Manual",
            channel_id="manual",
        )
        print("Result:", "SUCCESS" if ok else "FAILED")
        return

    print("=== YouTube Tactical Knowledge Incremental Ingest Start ===")
    summary = ingester.run_incremental_ingest(
        max_videos_per_channel=args.max_per_channel,
        target_channel_id=args.channel,
    )
    print("\n=== Execution Summary ===")
    print(f"- Channels Checked: {summary['channels_checked']}")
    print(f"- Videos Discovered: {summary['videos_discovered']}")
    print(f"- Transcripts Fetched: {summary['transcripts_fetched']}")
    print(f"- Transcripts Skipped: {summary['transcripts_skipped']}")
    print(f"- Errors: {summary['errors']}")
    print("=========================")


if __name__ == "__main__":
    main()
