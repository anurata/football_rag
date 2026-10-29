"""
Multi-Club Tactical Ingestion, Curation & 7-Layer Decomposition Orchestrator
(scripts/collect_all_clubs_tactics.py).

Targets:
  - All 20 J1 Clubs in the 2026/27 season
  - Any FC Tokyo Emperor's Cup opponents dynamically registered in config/target_clubs_config.json

Capabilities:
  1. Synchronizes 2026 club/manager/player ground-truth registry & team_tactical_profiles.json.
  2. Incremental multi-club YouTube video discovery across 14 tactical channels (--ingest).
  3. Multi-club transcript curation & ASR normalization.
  4. Decomposes mixed YouTube commentary into Manifesto Layers 1..7 via Gemini + Rule Fallback,
     persisting into SQLite (tactical_discourse_claims) and JSON.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.gemini_client import GeminiTacticalClient
from pipeline.club_entity_registry import ClubEntityRegistry
from pipeline.discourse_layer_decomposer import (
    DiscourseLayerDecomposer,
    TacticalDiscourseRepository,
)
from pipeline.official_discourse_ingester import (
    export_all_clubs_primary_dossiers,
    ingest_official_markdowns_into_layers,
)
from scripts.curate_and_clean_youtube_tactics import (
    NOISE_VIDEO_TITLE_TERMS,
    TACTICAL_VOCABULARY,
    classify_segment_topic,
    fetch_oembed_title,
    format_seconds,
    normalize_transcript_text,
)
from scripts.ingest_youtube_tactics import (
    CONFIG_PATH,
    HISTORY_PATH,
    PROFILES_PATH,
    RAW_YOUTUBE_DIR,
    YouTubeRateLimitError,
    YouTubeTacticalIngester,
    load_json_safely,
    save_json_safely,
)

logger = logging.getLogger("collect_all_clubs_tactics")

ROOT_DIR = Path(__file__).resolve().parent.parent
LAYERED_JSON_OUTPUT_PATH = ROOT_DIR / "data" / "curated" / "all_clubs_layered_claims.json"


def sync_all_clubs_into_tactical_profiles(
    registry: ClubEntityRegistry,
    profiles_path: Path = PROFILES_PATH,
) -> Dict[str, Any]:
    """
    Ensure all 20 J1 clubs + enabled Emperor's Cup opponents exist in
    knowledge/team_tactical_profiles.json with accurate 2026 official managers.
    """
    master = load_json_safely(profiles_path, {"version": "1.1.0", "teams": {}})
    teams_dict: Dict[str, Any] = master.setdefault("teams", {})
    now_iso = datetime.now(timezone.utc).isoformat()

    for club in registry.list_target_clubs():
        tid = club["team_id"]
        entry = teams_dict.setdefault(
            tid,
            {
                "team_id": tid,
                "team_name": club["canonical_name"],
                "base_formation": "4-4-2",
                "in_possession": {},
                "out_of_possession": {},
                "transitions": {},
                "structural_vulnerabilities": [],
                "evidences": [],
            },
        )
        # Always synchronize manager and scope to 2026 official ground truth
        entry["team_name"] = club["canonical_name"]
        entry["manager"] = club["current_manager"]
        entry["previous_managers_2026"] = club.get("previous_managers_2026", [])
        entry["competition_scope"] = club.get("competition_scope", "J1_2026")
        entry["key_players_2026"] = club.get("key_players", [])[:10]

    master["version"] = "1.2.0"
    master["updated_at"] = now_iso
    save_json_safely(profiles_path, master)
    return master


def ingest_videos_for_clubs(
    ingester: YouTubeTacticalIngester,
    registry: ClubEntityRegistry,
    target_team_ids: Optional[List[str]] = None,
    max_per_club_query: int = 2,
) -> Dict[str, int]:
    """
    Search general J-League tactical channels for each target club to fill gaps
    beyond FC Tokyo, deduplicating via ingest_history.json.
    """
    stats = {"discovered": 0, "fetched": 0, "errors": 0}
    clubs = registry.list_target_clubs()
    if target_team_ids:
        allowed = set(target_team_ids)
        clubs = [c for c in clubs if c["team_id"] in allowed]

    channels = [
        ch
        for ch in ingester.channels_config.get("channels", [])
        if ch.get("scan_mode") == "SEARCH_AND_RECENT" and int(ch.get("priority", 2)) == 1
    ]

    rate_limited = False
    for club in clubs:
        if rate_limited:
            break
        query = club["youtube_search_query"]
        for ch in channels:
            if rate_limited:
                break
            ch_id = ch.get("channel_id", "unknown")
            ch_name = ch.get("name", "Unknown")
            candidates = ingester.discover_new_videos(
                channel_info=ch,
                max_videos=max_per_club_query,
                search_query=query,
            )
            stats["discovered"] += len(candidates)
            for vid, title in candidates:
                if ingester.is_video_processed(vid):
                    continue
                try:
                    ok = ingester.process_single_video(
                        video_id=vid,
                        video_title=title,
                        channel_name=ch_name,
                        channel_id=ch_id,
                    )
                    time.sleep(1.5)
                except YouTubeRateLimitError as rle:
                    logger.warning("Circuit breaker tripped on %s: %s", vid, rle)
                    ingester.record_history(
                        video_id=vid,
                        channel_id=ch_id,
                        title=title,
                        status="RATE_LIMITED",
                        error_message=str(rle),
                    )
                    rate_limited = True
                    break

                if ok:
                    stats["fetched"] += 1
                else:
                    stats["errors"] += 1

    return stats


def _extract_multi_club_segments_from_video(
    video_data: Dict[str, Any],
    registry: ClubEntityRegistry,
    window_duration: float = 90.0,
    step_duration: float = 45.0,
    max_segment_duration: float = 240.0,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Scan a cached video across all target clubs (J1 20 + Cup Opponents),
    verifying 2026 active era and extracting tactical segments.
    """
    vid = str(video_data.get("video_id", "")).strip()
    ch_name = str(video_data.get("channel_name", "")).strip()
    cached_title = str(video_data.get("title", "")).strip()
    transcript = video_data.get("transcript", [])

    if not vid or not transcript:
        return ([], [])

    official_title = fetch_oembed_title(vid, fallback_title=cached_title)
    if any(noise in official_title for noise in NOISE_VIDEO_TITLE_TERMS):
        return ([], [])

    full_norm = normalize_transcript_text(
        " ".join(s.get("text", "") for s in transcript),
    )

    mentioned_ids = registry.detect_mentioned_clubs(official_title, full_norm)
    if not mentioned_ids:
        return ([], [])

    # Check 2026 era validity: require season tag or at least 1 active 2026 manager/key player
    active_era_tokens: Set[str] = {"26-27", "2026", "百年構想"}
    all_club_keywords: Set[str] = set()
    for tid in mentioned_ids:
        c_info = registry.get_club(tid) or {}
        all_club_keywords.update(c_info.get("entity_keywords", []))
        mgr = c_info.get("current_manager", "")
        if mgr and mgr != "監督":
            active_era_tokens.update(p for p in mgr.split(" ") if len(p) >= 2)
        for kp in c_info.get("key_players", [])[:8]:
            active_era_tokens.update(p for p in kp.split(" ") if len(p) >= 2)

    combined_scope = f"{official_title} {full_norm}"
    if not any(tok in combined_scope for tok in active_era_tokens):
        return ([], [])

    last_item = transcript[-1]
    total_dur = float(last_item.get("start", 0.0)) + float(last_item.get("duration", 0.0))
    cur_t = 0.0
    windows: List[Tuple[float, float, List[Dict[str, Any]]]] = []

    while cur_t < total_dur:
        w_end = cur_t + window_duration
        snips = [s for s in transcript if cur_t <= float(s.get("start", 0.0)) < w_end]
        w_text = normalize_transcript_text(" ".join(s.get("text", "") for s in snips))

        tac_hits = sum(1 for kw in TACTICAL_VOCABULARY if kw in w_text)
        ent_hits = sum(1 for kw in all_club_keywords if kw in w_text)
        if snips and ((tac_hits >= 2 and ent_hits >= 1) or tac_hits >= 3):
            windows.append((cur_t, w_end, snips))
        cur_t += step_duration

    if not windows:
        return ([], [])

    segments = _merge_windows_into_segments(
        video_id=vid,
        channel_name=ch_name,
        official_title=official_title,
        windows=windows,
        max_segment_duration=max_segment_duration,
    )
    return (mentioned_ids, segments)


def _merge_windows_into_segments(
    video_id: str,
    channel_name: str,
    official_title: str,
    windows: List[Tuple[float, float, List[Dict[str, Any]]]],
    max_segment_duration: float = 240.0,
) -> List[Dict[str, Any]]:
    """Merge contiguous windows into coherent 3-4 minute segments."""
    merged: List[Dict[str, Any]] = []
    cur_start, cur_end, cur_snips = windows[0][0], windows[0][1], list(windows[0][2])

    for w_start, w_end, snips in windows[1:]:
        exceeds = (max(cur_end, w_end) - cur_start) > max_segment_duration
        contiguous = w_start <= (cur_end + 30.0)

        if contiguous and not exceeds:
            cur_end = max(cur_end, w_end)
            for s in snips:
                if not any(ex.get("start") == s.get("start") for ex in cur_snips):
                    cur_snips.append(s)
        else:
            seg = _format_segment(video_id, channel_name, official_title, cur_start, cur_end, cur_snips)
            if seg:
                merged.append(seg)
            fresh = [s for s in snips if float(s.get("start", 0.0)) >= cur_end] or list(snips)
            cur_start = float(fresh[0].get("start", w_start))
            cur_end = w_end
            cur_snips = fresh

    last_seg = _format_segment(video_id, channel_name, official_title, cur_start, cur_end, cur_snips)
    if last_seg:
        merged.append(last_seg)
    return merged


def _format_segment(
    video_id: str,
    channel_name: str,
    official_title: str,
    start_sec: float,
    end_sec: float,
    snippets: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Format segment dict."""
    sorted_s = sorted(snippets, key=lambda x: float(x.get("start", 0.0)))
    text = normalize_transcript_text(" ".join(x.get("text", "") for x in sorted_s))
    if len(text) < 50:
        return None
    return {
        "segment_id": f"SEG_{video_id}_{int(start_sec)}",
        "video_id": video_id,
        "channel_name": channel_name,
        "video_title": official_title,
        "video_url": f"https://www.youtube.com/watch?v={video_id}&t={int(start_sec)}s",
        "time_range": f"{format_seconds(start_sec)} - {format_seconds(end_sec)}",
        "start_seconds": round(start_sec, 1),
        "end_seconds": round(end_sec, 1),
        "primary_topic": classify_segment_topic(text),
        "verbatim_text": text,
    }


def run_layer_decomposition_pipeline(
    registry: ClubEntityRegistry,
    repo: TacticalDiscourseRepository,
    raw_youtube_dir: Path = RAW_YOUTUBE_DIR,
    output_json_path: Path = LAYERED_JSON_OUTPUT_PATH,
    use_gemini: bool = True,
    gemini_segment_budget: int = 15,
) -> Dict[str, Any]:
    """
    Decompose cached videos across all target clubs into 7 Layers and store in SQLite + JSON.
    gemini_segment_budget limits synchronous LLM calls per run while seamlessly falling back
    to deterministic rules beyond budget (or 0 for instant deterministic pass).
    """
    club_map = {c["team_id"]: c for c in registry.list_target_clubs()}
    gemini_client = GeminiTacticalClient()
    decomposer_llm = DiscourseLayerDecomposer(
        gemini_client=gemini_client,
        club_profiles=club_map,
        use_gemini=use_gemini,
    )
    decomposer_rule = DiscourseLayerDecomposer(
        gemini_client=gemini_client,
        club_profiles=club_map,
        use_gemini=False,
    )

    all_claims: List[Dict[str, Any]] = []
    videos_processed = 0
    llm_calls_used = 0

    for f_path in sorted(glob.glob(str(raw_youtube_dir / "*.json"))):
        if "history" in Path(f_path).name:
            continue
        video_data = load_json_safely(Path(f_path))
        if not video_data:
            continue

        mentioned_ids, segments = _extract_multi_club_segments_from_video(
            video_data=video_data,
            registry=registry,
        )
        if not segments:
            continue

        videos_processed += 1
        for seg in segments:
            if use_gemini and llm_calls_used < gemini_segment_budget:
                claims = decomposer_llm.decompose_segment(seg, mentioned_ids)
                if any(c["extraction_method"] == "gemini_structured" for c in claims):
                    llm_calls_used += 1
            else:
                claims = decomposer_rule.decompose_segment(seg, mentioned_ids)

            repo.upsert_claims(claims)
            all_claims.extend(claims)

    layer_counts: Dict[str, int] = {}
    for c in all_claims:
        lname = c["layer_name"]
        layer_counts[lname] = layer_counts.get(lname, 0) + 1

    summary_payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "videos_processed": videos_processed,
        "total_claims_stored": len(all_claims),
        "gemini_segments_enriched": llm_calls_used,
        "layer_distribution": layer_counts,
        "club_layer_matrix": repo.count_by_team_and_layer(),
        "claims": all_claims,
    }
    save_json_safely(output_json_path, summary_payload)
    return summary_payload


def main() -> None:
    import sys

    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="J1 All 20 Clubs + FC Tokyo Emperor's Cup Tactical Collector & 7-Layer Decomposer",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Crawl YouTube channels to discover new videos for target clubs",
    )
    parser.add_argument(
        "--clubs",
        type=str,
        default=None,
        help="Comma-separated team_ids when running --ingest (e.g., KAS,URA,HIR,VOB)",
    )
    parser.add_argument(
        "--gemini-budget",
        type=int,
        default=10,
        help="Max segments to decompose via live Gemini API per batch (rest use deterministic fallback)",
    )
    parser.add_argument(
        "--register-cup-opponent",
        nargs=4,
        metavar=("TEAM_ID", "CLUB_NAME", "CATEGORY", "MANAGER"),
        help="Register an FC Tokyo Emperor's Cup opponent (e.g., VEG ベガルタ仙台 J2 森山佳郎)",
    )

    args = parser.parse_args()
    registry = ClubEntityRegistry()

    if args.register_cup_opponent:
        tid, cname, cat, mgr = args.register_cup_opponent
        entry = registry.register_emperor_cup_opponent(
            team_id=tid,
            canonical_name=cname,
            category=cat,
            current_manager=mgr,
            persist_to_config=True,
        )
        print(f"Registered Emperor's Cup opponent: {entry['team_id']} - {entry['canonical_name']} ({mgr})")

    reg_path = registry.export_registry_json()
    sync_all_clubs_into_tactical_profiles(registry)
    print(f"Synchronized {len(registry.list_target_clubs())} target clubs -> {reg_path}")

    if args.ingest:
        ingester = YouTubeTacticalIngester(
            config_path=CONFIG_PATH,
            history_path=HISTORY_PATH,
            raw_dir=RAW_YOUTUBE_DIR,
            profiles_path=PROFILES_PATH,
        )
        club_filter = [x.strip() for x in args.clubs.split(",")] if args.clubs else None
        ingest_stats = ingest_videos_for_clubs(
            ingester=ingester,
            registry=registry,
            target_team_ids=club_filter,
        )
        print(f"Ingest stats: {ingest_stats}")

    repo = TacticalDiscourseRepository()

    off_stats = ingest_official_markdowns_into_layers(
        registry=registry,
        repo=repo,
    )
    print(f"Official 2026 Press/Player Ingestion: {off_stats}")

    result = run_layer_decomposition_pipeline(
        registry=registry,
        repo=repo,
        use_gemini=(args.gemini_budget > 0),
        gemini_segment_budget=args.gemini_budget,
    )
    print(
        f"Completed YouTube 7-Layer Decomposition: {result['videos_processed']} videos -> "
        f"{result['total_claims_stored']} YouTube claims (Gemini segments: {result['gemini_segments_enriched']})",
    )

    exported_files = export_all_clubs_primary_dossiers(
        registry=registry,
        repo=repo,
    )
    print(f"Exported {len(exported_files)} club primary dossiers -> exports/clubs/")
    print("Club x Layer Matrix:", json.dumps(repo.count_by_team_and_layer(), ensure_ascii=False))


if __name__ == "__main__":
    main()

