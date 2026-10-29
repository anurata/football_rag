"""
Curated Video Selection, Hierarchical Coarse Text Scan & Transcript Normalization Pipeline
(scripts/curate_and_clean_youtube_tactics.py).

Improvements after self-review:
1. Accurate Video Metadata Acquisition via YouTube oEmbed API (with cached title fallback).
2. Two-tier Context-Aware Curation:
   - Tier A (Dedicated FC Tokyo Videos): Preserves full tactical discourse across the match
     (even when subject pronouns are omitted) and splits into readable 3-4 minute topic chunks.
   - Tier B (Multi-club General Videos): Captures the FC Tokyo section plus trailing tactical
     follow-up windows until topic shifts to unrelated clubs.
3. Smart Derby-Safe Exclusion Filter: Rejects standalone Verdy videos while keeping Tokyo Derby reviews.
4. Expanded Phonetic Normalization Dictionary based on empirical ASR errors.
"""

from __future__ import annotations

import glob
import json
import logging
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("curate_and_clean_youtube_tactics")

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_YOUTUBE_DIR = ROOT_DIR / "data" / "raw" / "youtube"
CURATED_OUTPUT_PATH = ROOT_DIR / "data" / "curated" / "youtube_tactical_segments.json"

DEDICATED_FCT_CHANNELS: Set[str] = {
    "トーキョウ二元論",
    "TOKYO OVERLAY",
    "ダメだ！フットボール",
    "tokyo_nigennron",
    "tokyo_overlay",
    "damedafootball",
}

# Phonetic correction dictionary for speech-to-text misrecognitions (pure ASR entity/term fixes)
PHONETIC_CORRECTIONS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"エ東京|江東京|石東京|ええ東京|SC東京|集東京"), "FC東京"),
    (re.compile(r"批安|ひあん|ヒ案|ヒアン"), "ヒアン"),
    (re.compile(r"マルセロヒアン|マルセロ\s*ヒアン|マルセロ・ヒアン|丸安"), "マルセロ・ヒアン"),
    (re.compile(r"アザソ相馬|安相マ|安相馬"), "安斎颯馬"),
    (re.compile(r"佐藤ケイ|佐藤ケ員|佐藤員"), "佐藤恵允"),
    (re.compile(r"山田風景|山田風(?!喜)"), "山田楓喜"),
    (re.compile(r"第2ゴメス|第2ゴメ|第 2ゴメ|ダニコメス|ラニゴメス|何ゴメス"), "ダニエル・ゴメス"),
    (re.compile(r"カシーフ|カシフ|カイフ|カ婦|カフ"), "佳史扶"),
    (re.compile(r"バングーナガンデ"), "バングーナガンデ"),
    (re.compile(r"力像"), "力蔵"),
    (re.compile(r"ブランチ|オランチ"), "ボランチ"),
    (re.compile(r"ミトホーリーホック|ミ戸"), "水戸ホーリーホック"),
    (re.compile(r"カシュアルイソル|レーソル|レイソル"), "柏レイソル"),
    (re.compile(r"東京ベルディ|ベルディ"), "東京ヴェルディ"),
    (re.compile(r"ゼルビア|町田ゼルビア"), "町田ゼルビア"),
    (re.compile(r"ペナカド|ペナ角"), "ペナルティエリア角（ポケット）"),
]

STANDALONE_VERDY_TERMS: Set[str] = {
    "東京ヴェルディ",
    "ヴェルディ",
}

CURRENT_ERA_MARKERS: Set[str] = {
    "26-27",
    "2026",
    "百年構想",
    "松橋",
    "力蔵",
    "稲村",
    "ショルツ",
    "長倉",
    "佐藤恵允",
    "マルセロ",
    "ヒアン",
    "スンギュ",
    "安斎",
    "ダニエル・ゴメス",
    "山田楓喜",
    "大森",
}

NOISE_VIDEO_TITLE_TERMS: Set[str] = {
    "チャント",
    "You'll Never Walk Alone",
    "グッズ売り場",
    "スタジアムグルメ",
    "キーボード ショートカット",
    "イーフト",
    "eFootball",
    "ウイイレ",
    "祝勝会場",
    "事故編集版",
    "ブルーノ・コウチーニョ",
}

FCT_ENTITY_KEYWORDS: Set[str] = {
    "FC東京",
    "松橋",
    "力蔵",
    "マルセロ",
    "ヒアン",
    "仲川",
    "俵積田",
    "室屋",
    "長友",
    "小泉",
    "高宇洋",
    "稲村",
    "ショルツ",
    "佐藤恵允",
    "長倉",
    "遠藤",
    "佳史扶",
    "バングーナガンデ",
    "白井",
    "岡哲平",
    "スンギュ",
    "野澤",
    "安斎",
    "石原",
    "山田楓喜",
    "ダニエル・ゴメス",
    "東慶悟",
    "大森",
}

TACTICAL_VOCABULARY: Set[str] = {
    "監督",
    "戦術",
    "システム",
    "フォーメーション",
    "4-4-2",
    "4-2-1-3",
    "3バック",
    "4バック",
    "ビルドアップ",
    "ハイプレス",
    "プレス",
    "ハイライン",
    "ライン",
    "ブロック",
    "ローブロック",
    "コンパクト",
    "背後",
    "裏抜け",
    "裏",
    "スルーパス",
    "フィード",
    "ロングボール",
    "ポケット",
    "ペナルティエリア",
    "ハーフスペース",
    "バイタル",
    "ボランチ",
    "サイドバック",
    "センターバック",
    "ウイング",
    "サイドハーフ",
    "2トップ",
    "シャドー",
    "距離感",
    "スライド",
    "セカンドボール",
    "保持",
    "ポゼッション",
    "カウンター",
    "ショートカウンター",
    "トランジション",
    "ネガトラ",
    "交代",
    "スタメン",
    "ポジショニング",
    "配置",
    "優位性",
    "数的優位",
    "質的優位",
    "クロス",
    "カットイン",
    "シュート",
    "決定機",
    "ゴール期待値",
    "xG",
    "パス本数",
    "前進",
    "守備",
    "攻撃",
    "採点",
    "リスク管理",
    "セットプレー",
    "コーナー",
}


def format_seconds(seconds: float) -> str:
    """Format seconds into MM:SS."""
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins:02d}:{secs:02d}"


def fetch_oembed_title(video_id: str, fallback_title: str = "") -> str:
    """Fetch accurate official video title using YouTube oEmbed API."""
    url = (
        f"https://www.youtube.com/oembed?"
        f"url=https://www.youtube.com/watch?v={video_id}&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            title = unicodedata.normalize("NFKC", str(data.get("title", "")).strip())
            if title:
                return title
    except Exception as e:
        logger.warning("Failed to fetch oEmbed title for %s: %s", video_id, e)

    if fallback_title and fallback_title != "YouTube Video":
        return unicodedata.normalize("NFKC", fallback_title)
    return f"YouTube Video ({video_id})"


def normalize_transcript_text(text: str) -> str:
    """Apply NFKC normalization, ASR phonetic corrections, and clean non-speech tags."""
    nfkc_text = unicodedata.normalize("NFKC", text)
    cleaned = re.sub(r"\[(?:音楽|笑い|拍手|歓声|咳払い|鼻息)\]", " ", nfkc_text)
    for pattern, replacement in PHONETIC_CORRECTIONS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def classify_segment_topic(text: str) -> str:
    """Classify the primary tactical theme of a segment deterministically."""
    if any(k in text for k in ["採点", "7.5", "6.5", "6.0", "5.5", "マンオブザマッチ"]):
        return "PLAYER_TACTICAL_EVALUATION"
    if any(k in text for k in ["ゴール期待値", "xG", "保持率", "データ", "本つないでも", "チャート"]):
        return "DATA_AND_GAME_FLOW"
    if any(k in text for k in ["背後", "裏抜け", "スルーパス", "ポケット", "クロス", "カットイン"]):
        return "ATTACKING_PATTERN_AND_IN_BEHIND"
    if any(k in text for k in ["ビルドアップ", "前進", "持たされた", "優位性", "配置", "ボランチ"]):
        return "BUILDUP_AND_POSITIONING"
    if any(k in text for k in ["ハイプレス", "ブロック", "リスク管理", "クリーンシート", "カウンター"]):
        return "DEFENSIVE_BLOCK_AND_TRANSITION"
    if any(k in text for k in ["交代", "ベンチ", "後半から", "投入"]):
        return "SUBSTITUTION_AND_MANAGEMENT"
    return "TACTICAL_ANALYSIS"


def build_video_summary(
    official_title: str,
    segments: List[Dict[str, Any]],
    is_dedicated: bool,
) -> str:
    """Generate an objective structural summary of tactical contents in the video."""
    if not segments:
        return ""

    combined = " ".join(s.get("verbatim_text", "") for s in segments)
    mentioned_entities = sorted([kw for kw in FCT_ENTITY_KEYWORDS if kw in combined])
    mentioned_tactics = sorted([kw for kw in TACTICAL_VOCABULARY if kw in combined])
    topics = list(dict.fromkeys(s.get("primary_topic", "") for s in segments))

    mode_str = "FC東京特化・全編戦術分析" if is_dedicated else "J1横断・FC東京戦術パート抽出"
    total_chars = sum(len(s.get("verbatim_text", "")) for s in segments)
    top_entities = "、".join(mentioned_entities[:8]) if mentioned_entities else "FC東京"
    top_tactics = "、".join(mentioned_tactics[:10]) if mentioned_tactics else "戦術全般"
    topic_str = ", ".join(topics)

    return (
        f"[{mode_str} | {len(segments)}セグメント / 計{total_chars:,}文字] "
        f"主要言及: {top_entities}。 "
        f"戦術論点({topic_str}): {top_tactics}。"
    )


class TacticalTranscriptCurator:
    """
    Screens YouTube transcripts with two-tier context-aware density scan,
    extracts rich multi-minute tactical segments, and normalizes verbatim quotes.
    """

    def __init__(
        self,
        raw_youtube_dir: Path = RAW_YOUTUBE_DIR,
        output_path: Path = CURATED_OUTPUT_PATH,
    ) -> None:
        self.raw_youtube_dir = raw_youtube_dir
        self.output_path = output_path
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def _is_noise_or_unrelated_video(
        self,
        official_title: str,
        full_normalized_text: str,
    ) -> bool:
        """Reject gaming videos, chant logs, or standalone Verdy matches without FC Tokyo."""
        norm_title = unicodedata.normalize("NFKC", official_title)

        if any(term in norm_title for term in NOISE_VIDEO_TITLE_TERMS):
            return True

        has_fct_in_title = any(
            kw in norm_title
            for kw in ["FC東京", "東京ダービー", "ダービー", "力蔵", "安斎", "長倉", "ヒアン"]
        )
        has_verdy_in_title = any(v in norm_title for v in STANDALONE_VERDY_TERMS)

        # If title explicitly specifies a Tokyo Verdy match without FC Tokyo or Derby -> Reject
        if has_verdy_in_title and not has_fct_in_title:
            return True

        fct_hits_in_body = sum(1 for kw in FCT_ENTITY_KEYWORDS if kw in full_normalized_text)
        has_verdy = has_verdy_in_title or any(
            v in full_normalized_text for v in STANDALONE_VERDY_TERMS
        )

        # Standalone Verdy video (no FC Tokyo presence) -> Reject
        if has_verdy and not has_fct_in_title and fct_hits_in_body == 0:
            return True

        # Zero FC Tokyo entities anywhere -> Reject
        if not has_fct_in_title and fct_hits_in_body == 0:
            return True

        # Reject outdated pre-2026 seasons lacking any current-era coach/player/season marker
        combined_scope = f"{norm_title} {full_normalized_text}"
        if not any(marker in combined_scope for marker in CURRENT_ERA_MARKERS):
            return True

        return False

    def _is_dedicated_fct_video(
        self,
        channel_name: str,
        channel_id: str,
        official_title: str,
        full_normalized_text: str,
    ) -> bool:
        """Determine whether the entire video is dedicated to FC Tokyo match/tactics."""
        fct_title_markers = [
            "FC東京",
            "東京ダービー",
            "力蔵",
            "安斎颯馬",
            "マルセロ",
            "俵積田",
            "仲川輝人",
            "稲村",
            "長倉",
        ]
        if any(m in official_title for m in fct_title_markers):
            return True

        if channel_name in DEDICATED_FCT_CHANNELS or channel_id in DEDICATED_FCT_CHANNELS:
            fct_hits = sum(1 for kw in FCT_ENTITY_KEYWORDS if kw in full_normalized_text)
            if fct_hits >= 2:
                return True

        return False

    def _evaluate_window(
        self,
        normalized_win_text: str,
        is_dedicated: bool,
        carryover_frames: int,
    ) -> Tuple[bool, int]:
        """
        Evaluate whether a 60s window should be kept.
        Returns (keep_window, updated_carryover_frames).
        """
        entity_hits = sum(1 for kw in FCT_ENTITY_KEYWORDS if kw in normalized_win_text)
        tactical_hits = sum(1 for kw in TACTICAL_VOCABULARY if kw in normalized_win_text)

        # Reject standalone Verdy talk when zero FC Tokyo entities and not dedicated derby review
        if not is_dedicated and entity_hits == 0:
            if any(v in normalized_win_text for v in STANDALONE_VERDY_TERMS):
                return (False, 0)

        if is_dedicated:
            # In a dedicated FC Tokyo video, keep any window containing tactical/match analysis
            keep = (tactical_hits >= 2) or (entity_hits >= 1 and tactical_hits >= 1) or (entity_hits >= 2)
            return (keep, 0)

        # Multi-club video: start capturing when FC Tokyo entity co-occurs with tactics,
        # and allow 1-2 windows of carryover if tactical explanation continues via pronouns.
        if (entity_hits >= 1 and tactical_hits >= 2) or (entity_hits >= 2):
            return (True, 2)

        if carryover_frames > 0 and tactical_hits >= 2:
            return (True, carryover_frames - 1)

        return (False, 0)

    def scan_video_hotspots(
        self,
        video_id: str,
        channel_name: str,
        official_title: str,
        transcript: List[Dict[str, Any]],
        window_duration: float = 60.0,
        step_duration: float = 30.0,
        channel_id: str = "",
        max_segment_duration: float = 240.0,
    ) -> List[Dict[str, Any]]:
        """
        Execute hierarchical context-aware scan over video transcript.
        Returns rich, coherent tactical discussion segments.
        """
        if not transcript:
            return []

        raw_full = " ".join(s.get("text", "") for s in transcript)
        full_normalized = normalize_transcript_text(raw_full)

        if self._is_noise_or_unrelated_video(official_title, full_normalized):
            return []

        is_dedicated = self._is_dedicated_fct_video(
            channel_name=channel_name,
            channel_id=channel_id,
            official_title=official_title,
            full_normalized_text=full_normalized,
        )

        # Require minimum tactical substance across whole video
        total_tactical_terms = sum(1 for kw in TACTICAL_VOCABULARY if kw in full_normalized)
        if total_tactical_terms < 2:
            return []

        last_item = transcript[-1]
        total_duration = float(last_item.get("start", 0.0)) + float(last_item.get("duration", 0.0))
        current_time = 0.0
        carryover = 0
        hotspot_windows: List[Tuple[float, float, List[Dict[str, Any]]]] = []

        while current_time < total_duration:
            win_end = current_time + window_duration
            snippets_in_win = [
                s for s in transcript if current_time <= float(s.get("start", 0.0)) < win_end
            ]
            win_text = normalize_transcript_text(
                " ".join(s.get("text", "") for s in snippets_in_win),
            )

            keep, carryover = self._evaluate_window(
                normalized_win_text=win_text,
                is_dedicated=is_dedicated,
                carryover_frames=carryover,
            )
            if keep and snippets_in_win:
                hotspot_windows.append((current_time, win_end, snippets_in_win))

            current_time += step_duration

        if not hotspot_windows:
            return []

        gap_tolerance = 45.0 if is_dedicated else 20.0
        return self._merge_hotspot_windows(
            video_id=video_id,
            channel_name=channel_name,
            official_title=official_title,
            windows=hotspot_windows,
            gap_tolerance=gap_tolerance,
            max_segment_duration=max_segment_duration,
        )

    def _merge_hotspot_windows(
        self,
        video_id: str,
        channel_name: str,
        official_title: str,
        windows: List[Tuple[float, float, List[Dict[str, Any]]]],
        gap_tolerance: float = 30.0,
        max_segment_duration: float = 240.0,
    ) -> List[Dict[str, Any]]:
        """
        Merge contiguous hotspot windows while splitting at logical ~4 minute boundaries
        so each tactical block stays focused, readable, and granular.
        """
        merged: List[Dict[str, Any]] = []
        if not windows:
            return merged

        cur_start = windows[0][0]
        cur_end = windows[0][1]
        all_snippets: List[Dict[str, Any]] = list(windows[0][2])

        for w_start, w_end, snips in windows[1:]:
            would_exceed_max = (max(cur_end, w_end) - cur_start) > max_segment_duration
            is_contiguous = w_start <= (cur_end + gap_tolerance)

            if is_contiguous and not would_exceed_max:
                cur_end = max(cur_end, w_end)
                for s in snips:
                    if not any(ex.get("start") == s.get("start") for ex in all_snippets):
                        all_snippets.append(s)
            else:
                seg = self._build_segment_dict(
                    video_id=video_id,
                    channel_name=channel_name,
                    official_title=official_title,
                    start_sec=cur_start,
                    end_sec=cur_end,
                    snippets=all_snippets,
                )
                if seg:
                    merged.append(seg)

                # For split chunks, start from non-overlapping snippets after cur_end
                fresh_snips = [s for s in snips if float(s.get("start", 0.0)) >= cur_end]
                if not fresh_snips:
                    fresh_snips = list(snips)
                    cur_start = w_start
                else:
                    cur_start = float(fresh_snips[0].get("start", w_start))
                cur_end = w_end
                all_snippets = fresh_snips

        seg = self._build_segment_dict(
            video_id=video_id,
            channel_name=channel_name,
            official_title=official_title,
            start_sec=cur_start,
            end_sec=cur_end,
            snippets=all_snippets,
        )
        if seg:
            merged.append(seg)

        return merged

    def _build_segment_dict(
        self,
        video_id: str,
        channel_name: str,
        official_title: str,
        start_sec: float,
        end_sec: float,
        snippets: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Construct normalized segment payload with verbatim speech paragraphs."""
        sorted_snips = sorted(snippets, key=lambda s: float(s.get("start", 0.0)))
        raw_combined = " ".join(s.get("text", "") for s in sorted_snips)
        cleaned_text = normalize_transcript_text(raw_combined)

        if len(cleaned_text) < 50:
            return None

        primary_topic = classify_segment_topic(cleaned_text)

        return {
            "segment_id": f"SEG_{video_id}_{int(start_sec)}",
            "video_id": video_id,
            "channel_name": channel_name,
            "video_title": official_title,
            "video_url": f"https://www.youtube.com/watch?v={video_id}&t={int(start_sec)}s",
            "time_range": f"{format_seconds(start_sec)} - {format_seconds(end_sec)}",
            "start_seconds": round(start_sec, 1),
            "end_seconds": round(end_sec, 1),
            "char_count": len(cleaned_text),
            "primary_topic": primary_topic,
            "verbatim_text": cleaned_text,
        }

    def curate_all_cached_videos(self) -> Dict[str, Any]:
        """Process all cached JSON videos and produce curated video summaries + segments."""
        all_segments: List[Dict[str, Any]] = []
        curated_videos: List[Dict[str, Any]] = []

        json_files = sorted(glob.glob(str(self.raw_youtube_dir / "*.json")))
        for f_path in json_files:
            if "history" in Path(f_path).name:
                continue

            try:
                with open(f_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
            except Exception:
                continue

            vid = str(data.get("video_id", "")).strip()
            ch_name = str(data.get("channel_name", "")).strip()
            ch_id = str(data.get("channel_id", "")).strip()
            cached_title = str(data.get("title", "")).strip()
            transcript = data.get("transcript", [])

            if not vid or not transcript:
                continue

            official_title = fetch_oembed_title(vid, fallback_title=cached_title)
            raw_full = normalize_transcript_text(
                " ".join(s.get("text", "") for s in transcript),
            )
            is_dedicated = self._is_dedicated_fct_video(
                channel_name=ch_name,
                channel_id=ch_id,
                official_title=official_title,
                full_normalized_text=raw_full,
            )

            segments = self.scan_video_hotspots(
                video_id=vid,
                channel_name=ch_name,
                official_title=official_title,
                transcript=transcript,
                channel_id=ch_id,
            )
            if not segments:
                continue

            summary_text = build_video_summary(
                official_title=official_title,
                segments=segments,
                is_dedicated=is_dedicated,
            )
            curated_videos.append(
                {
                    "video_id": vid,
                    "channel_name": ch_name,
                    "channel_id": ch_id,
                    "video_title": official_title,
                    "video_url": f"https://www.youtube.com/watch?v={vid}",
                    "is_dedicated_fct": is_dedicated,
                    "segment_count": len(segments),
                    "total_chars": sum(s["char_count"] for s in segments),
                    "tactical_summary": summary_text,
                },
            )
            all_segments.extend(segments)

        payload = {
            "total_curated_videos": len(curated_videos),
            "total_curated_segments": len(all_segments),
            "total_verbatim_chars": sum(s["char_count"] for s in all_segments),
            "videos": curated_videos,
            "segments": all_segments,
        }
        with open(self.output_path, "w", encoding="utf-8") as out:
            json.dump(payload, out, ensure_ascii=False, indent=2)

        return payload


def main() -> None:
    import sys

    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    curator = TacticalTranscriptCurator()
    print("=== Starting Two-Tier Curated Video Selection & Deep Text Scan ===")
    result = curator.curate_all_cached_videos()
    print(
        f"\n[Finished] Videos Curated: {result['total_curated_videos']} | "
        f"Segments: {result['total_curated_segments']} | "
        f"Total Verbatim Chars: {result['total_verbatim_chars']:,}",
    )
    for v in result["videos"]:
        print(f" - [{v['channel_name']}] {v['video_title']}")
        print(f"   {v['tactical_summary']}")


if __name__ == "__main__":
    main()
