"""2026 J1 全試合の Yahoo!サッカー /summary（時間帯別フォーメーション・ピッチ座標）取得スクリプト.

Usage:
    python -m scripts.fetch_yahoo_summaries_2026 --start-mw 1 --end-mw 12
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.normalizer import EntityNormalizer
from scrapers.yahoo_soccer import YahooSoccerScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fetch_yahoo_summaries_2026")


def load_db_matches_lookup(db_path: Path) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """football.db の 2026 シーズン試合一覧を (home_team_id, away_team_id) で引ける辞書にする."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT match_id, matchweek, date, home_team_id, away_team_id
            FROM matches
            WHERE season = 2026
            """,
        )
        lookup: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for r in cur.fetchall():
            key = (r["home_team_id"], r["away_team_id"])
            lookup.setdefault(key, []).append(dict(r))
        return lookup
    finally:
        conn.close()


def resolve_canonical_match_id(
    game_id: str,
    summary_data: Dict[str, Any],
    normalizer: EntityNormalizer,
    db_lookup: Dict[Tuple[str, str], List[Dict[str, Any]]],
) -> str:
    """Yahooのgame_idとチーム名から football.db の正規 match_id (YYYYMMDD_HOME_AWAY) を特定する."""
    info = summary_data.get("match_info", {})
    h_raw = info.get("home_team", "")
    a_raw = info.get("away_team", "")
    h_id = normalizer.normalize_team_name(h_raw) or h_raw
    a_id = normalizer.normalize_team_name(a_raw) or a_raw

    candidates = db_lookup.get((h_id, a_id), [])
    date_prefix = f"{game_id[:4]}-{game_id[4:6]}-{game_id[6:8]}" if len(game_id) >= 8 else ""

    for cand in candidates:
        if cand.get("date") == date_prefix:
            return cand["match_id"]
    if candidates:
        return candidates[0]["match_id"]

    return f"{game_id[:8]}_{h_id}_{a_id}"


def run_batch_fetch(
    start_mw: int = 1,
    end_mw: int = 12,
    output_dir: Path = ROOT_DIR / "data" / "raw" / "yahoo",
    db_path: Path = ROOT_DIR / "data" / "football.db",
    sleep_sec: float = 0.4,
    force: bool = False,
) -> Dict[str, Any]:
    """指定節範囲のYahoo /summaryを一括取得し、match_idと紐づけてキャッシュ保存する."""
    os.makedirs(output_dir, exist_ok=True)
    scraper = YahooSoccerScraper()
    normalizer = EntityNormalizer()
    db_lookup = load_db_matches_lookup(db_path)

    map_path = output_dir / "game_id_map_2026.json"
    existing_map: Dict[str, str] = {}
    if map_path.exists():
        try:
            existing_map = json.loads(map_path.read_text(encoding="utf-8"))
        except Exception:
            existing_map = {}

    mw_gids = scraper.fetch_schedule_game_ids(start_mw=start_mw, end_mw=end_mw)
    all_pairs: List[Tuple[int, str]] = [
        (mw, gid) for mw, gids in sorted(mw_gids.items()) for gid in gids
    ]
    logger.info("Discovered %d Yahoo game_ids across MW%d..MW%d", len(all_pairs), start_mw, end_mw)

    fetched = 0
    skipped = 0
    errors = 0

    for idx, (mw, gid) in enumerate(all_pairs, start=1):
        known_mid = existing_map.get(gid)
        if known_mid and not force:
            cached_file = output_dir / f"{known_mid}_summary.json"
            if cached_file.exists() and cached_file.stat().st_size > 200:
                skipped += 1
                continue

        try:
            summary = scraper.fetch_summary(gid)
            match_id = resolve_canonical_match_id(gid, summary, normalizer, db_lookup)
            summary["match_id"] = match_id
            summary["matchweek_scraped"] = mw

            out_file = output_dir / f"{match_id}_summary.json"
            out_file.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            existing_map[gid] = match_id
            fetched += 1
            if fetched % 15 == 0 or idx == len(all_pairs):
                logger.info(
                    "[%d/%d] Fetched %s -> %s (snapshots=%d)",
                    idx,
                    len(all_pairs),
                    gid,
                    match_id,
                    len(summary.get("formation_snapshots", [])),
                )
            time.sleep(sleep_sec)
        except Exception as exc:
            errors += 1
            logger.warning("[%d/%d] Failed %s: %s", idx, len(all_pairs), gid, exc)
            time.sleep(1.0)

    map_path.write_text(
        json.dumps(existing_map, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "discovered": len(all_pairs),
        "fetched": fetched,
        "skipped": skipped,
        "errors": errors,
        "mapped_total": len(existing_map),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Yahoo /summary formation snapshots.")
    parser.add_argument("--start-mw", type=int, default=1)
    parser.add_argument("--end-mw", type=int, default=12)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    stats = run_batch_fetch(
        start_mw=args.start_mw,
        end_mw=args.end_mw,
        sleep_sec=args.sleep,
        force=args.force,
    )
    logger.info("Batch summary fetch completed: %s", stats)


if __name__ == "__main__":
    main()

