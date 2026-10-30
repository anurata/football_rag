"""2026年J1全120試合 3ソース個人・チームスタッツ一括取得＆DB格納スクリプト (scripts/fetch_all_2026_match_stats.py).

機能:
- `data/raw/yahoo/game_id_map_2026.json` と `football.db` を参照し、
  未取得の108試合について Yahoo `/stats`, SPAIA `live_player_detail_stats`, Football LAB `report` を取得・JSON保存。
- 取得済みの正規データ（FC東京12試合等）は自動スキップ（中断再開可能）。
- 取得完了後に `pipeline/player_stats_ingester.py` で全120試合の `player_match_stats` / `team_match_stats` をDB格納。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.player_stats_ingester import ingest_all_2026_player_and_team_stats
from pipeline.tactical_position_resolver import TacticalPositionResolver
from scrapers.football_lab import FootballLabScraper
from scrapers.spaia_soccer import SpaiasoccerScraper
from scrapers.yahoo_soccer import YahooSoccerScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fetch_all_2026_match_stats")


def _has_nonempty_list(json_path: Path, *keys: str) -> bool:
    """指定JSONパス内のネストキーが非空リストを持つか判定する."""
    if not json_path.exists():
        return False
    try:
        cur: Any = json.loads(json_path.read_text(encoding="utf-8"))
        for k in keys:
            if not isinstance(cur, dict):
                return False
            cur = cur.get(k)
        return isinstance(cur, list) and len(cur) > 0
    except Exception:
        return False


def _fetch_yahoo_if_needed(
    scraper: YahooSoccerScraper,
    game_id: str,
    match_id: str,
    yahoo_dir: Path,
    force: bool,
) -> str:
    """Yahoo `/stats` が未取得の場合のみ取得して保存する."""
    out_path = yahoo_dir / f"{match_id}_stats.json"
    if not force and _has_nonempty_list(out_path, "player_stats"):
        return "SKIPPED"
    data = scraper.fetch_stats(game_id)
    data["match_id"] = match_id
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return "FETCHED" if data.get("player_stats") else "EMPTY"


def _fetch_spaia_if_needed(
    scraper: SpaiasoccerScraper,
    game_id: str,
    match_id: str,
    spaia_dir: Path,
    force: bool,
) -> str:
    """SPAIA `live_player_detail_stats` が未取得の場合のみ取得して保存する."""
    out_path = spaia_dir / f"{match_id}_player_stats.json"
    if not force and _has_nonempty_list(out_path, "player_stats"):
        return "SKIPPED"
    pstats = scraper.fetch_player_detail_stats(game_id)
    payload = {
        "game_id": game_id,
        "match_id": match_id,
        "count": len(pstats),
        "player_stats": pstats,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return "FETCHED" if pstats else "EMPTY"


def _fetch_flab_if_needed(
    scraper: FootballLabScraper,
    match_id: str,
    date_str: str,
    home_team_id: str,
    away_team_id: str,
    flab_dir: Path,
    force: bool,
) -> str:
    """Football LAB マッチレポートJSON（CBP含む）が未取得の場合のみ取得してJSON保存する."""
    out_path = flab_dir / f"{match_id}.json"
    if not force and _has_nonempty_list(out_path, "data", "cbp", "player_matrix"):
        return "SKIPPED"

    data: Optional[Dict[str, Any]] = None
    for cand_tid in (home_team_id, away_team_id):
        url = scraper.build_match_url(cand_tid, date_str)
        if not url:
            continue
        try:
            fetched = scraper.fetch_match_data(url)
            if fetched.get("cbp", {}).get("player_matrix") or fetched.get("stats"):
                data = fetched
                break
        except Exception:
            continue

    if not data:
        return "FAILED"

    payload = {
        "match_id": match_id,
        "date": date_str,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "data": data,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return "FETCHED"


def load_2026_target_matches(
    db_path: Path,
    game_map_path: Path,
) -> List[Dict[str, Any]]:
    """DBと game_id_map_2026.json を突き合わせて全120試合の取得メタリストを返す."""
    gid_to_mid: Dict[str, str] = json.loads(game_map_path.read_text(encoding="utf-8"))
    mid_to_gid: Dict[str, str] = {mid: gid for gid, mid in gid_to_mid.items()}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT match_id, matchweek, date, home_team_id, away_team_id
            FROM matches
            WHERE season = 2026
            ORDER BY matchweek, date, match_id
            """,
        ).fetchall()
    finally:
        conn.close()

    targets: List[Dict[str, Any]] = []
    for r in rows:
        mid = r["match_id"]
        gid = mid_to_gid.get(mid, "")
        if not gid:
            sum_f = db_path.parent / "raw" / "yahoo" / f"{mid}_summary.json"
            if sum_f.exists():
                gid = json.loads(sum_f.read_text(encoding="utf-8")).get("game_id", "")
        targets.append(
            {
                "match_id": mid,
                "game_id": gid,
                "matchweek": r["matchweek"],
                "date": r["date"],
                "home_team_id": r["home_team_id"],
                "away_team_id": r["away_team_id"],
            },
        )
    return targets


def run_batch_stats_fetch(
    db_path: Path = ROOT_DIR / "data" / "football.db",
    raw_dir: Path = ROOT_DIR / "data" / "raw",
    sleep_sec: float = 0.25,
    force: bool = False,
) -> Dict[str, Any]:
    """全120試合分の3ソーススタッツを取得する（異ドメイン並列・同ドメイン順次ウェイト）."""
    yahoo_dir = raw_dir / "yahoo"
    spaia_dir = raw_dir / "spaia"
    flab_dir = raw_dir / "football_lab"
    yahoo_dir.mkdir(parents=True, exist_ok=True)
    spaia_dir.mkdir(parents=True, exist_ok=True)
    flab_dir.mkdir(parents=True, exist_ok=True)

    targets = load_2026_target_matches(db_path, yahoo_dir / "game_id_map_2026.json")
    y_scraper = YahooSoccerScraper()
    s_scraper = SpaiasoccerScraper()
    f_scraper = FootballLabScraper()

    counts = {
        "yahoo_fetched": 0,
        "spaia_fetched": 0,
        "flab_fetched": 0,
        "errors": 0,
    }

    for idx, t in enumerate(targets, start=1):
        mid = t["match_id"]
        gid = t["game_id"]
        if not gid:
            logger.warning("[%d/%d] Missing game_id for %s", idx, len(targets), mid)
            counts["errors"] += 1
            continue

        did_network = False
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                fut_y = pool.submit(_fetch_yahoo_if_needed, y_scraper, gid, mid, yahoo_dir, force)
                fut_s = pool.submit(_fetch_spaia_if_needed, s_scraper, gid, mid, spaia_dir, force)
                fut_f = pool.submit(
                    _fetch_flab_if_needed,
                    f_scraper,
                    mid,
                    t["date"],
                    t["home_team_id"],
                    t["away_team_id"],
                    flab_dir,
                    force,
                )
                res_y = fut_y.result()
                res_s = fut_s.result()
                res_f = fut_f.result()

            if res_y == "FETCHED":
                counts["yahoo_fetched"] += 1
                did_network = True
            if res_s == "FETCHED":
                counts["spaia_fetched"] += 1
                did_network = True
            if res_f == "FETCHED":
                counts["flab_fetched"] += 1
                did_network = True
            if "FAILED" in (res_y, res_s, res_f):
                counts["errors"] += 1

            if idx % 15 == 0 or idx == len(targets):
                logger.info(
                    "[%d/%d] Progress %s (MW%s) -> Y:%s S:%s FL:%s | totals=%s",
                    idx,
                    len(targets),
                    mid,
                    t["matchweek"],
                    res_y,
                    res_s,
                    res_f,
                    counts,
                )
        except Exception as exc:
            counts["errors"] += 1
            logger.warning("[%d/%d] Error on %s (%s): %s", idx, len(targets), mid, gid, exc)

        if did_network:
            time.sleep(sleep_sec)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch all 2026 match telemetry & ingest into football.db")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if cached")
    parser.add_argument("--ingest-only", action="store_true", help="Skip network fetch and only ingest cached JSON")
    args = parser.parse_args()

    if not args.ingest_only:
        fetch_summary = run_batch_stats_fetch(force=args.force)
        logger.info("Fetch summary: %s", json.dumps(fetch_summary, ensure_ascii=False))

    ingest_summary = ingest_all_2026_player_and_team_stats()
    logger.info("DB Ingest summary: %s", json.dumps(ingest_summary, ensure_ascii=False))

    # Re-run position resolver so SPAIA BOTH_FLANKS fluidity tags also benefit from all 120 SPAIA files!
    pos_summary = TacticalPositionResolver().resolve_all_2026_matches()
    logger.info("Position fluidity refresh: %s", json.dumps(pos_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

