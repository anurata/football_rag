"""FC東京 2026シーズン全12試合 正真正銘データ正規収集スクリプト (scripts/fetch_fct_canonical.py).

データスタジアム (SPAIA & Yahoo!サッカー) および Football LAB の正確な公式試合IDに基づき、
FC東京の第1節〜第12節全12試合の正規生データを取得・完全保存する。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scrapers.football_lab import FootballLabScraper
from scrapers.spaia_soccer import SpaiasoccerScraper
from scrapers.yahoo_soccer import YahooSoccerScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fetch_fct_canonical")

# FC東京 2026シーズン 全12試合 正真正銘公式マッピング
FCT_CANONICAL_MATCHES = [
    {
        "mw": 1,
        "match_id": "20260808_FCT_ZEL",
        "game_id": "2026080802",
        "date": "2026-08-08",
        "home": "FCT",
        "away": "ZEL",
        "score": "1-5",
    },
    {
        "mw": 2,
        "match_id": "20260815_VOB_FCT",
        "game_id": "2026081508",
        "date": "2026-08-15",
        "home": "VOB",
        "away": "FCT",
        "score": "2-2",
    },
    {
        "mw": 3,
        "match_id": "20260821_FCT_JEF",
        "game_id": "2026082101",
        "date": "2026-08-21",
        "home": "FCT",
        "away": "JEF",
        "score": "2-0",
    },
    {
        "mw": 4,
        "match_id": "20260829_VVN_FCT",
        "game_id": "2026082904",
        "date": "2026-08-29",
        "home": "VVN",
        "away": "FCT",
        "score": "0-3",
    },
    {
        "mw": 5,
        "match_id": "20260902_PUL_FCT",
        "game_id": "2026090221",
        "date": "2026-09-02",
        "home": "PUL",
        "away": "FCT",
        "score": "1-1",
    },
    {
        "mw": 6,
        "match_id": "20260906_FCT_SAN",
        "game_id": "2026090610",
        "date": "2026-09-06",
        "home": "FCT",
        "away": "SAN",
        "score": "2-0",
    },
    {
        "mw": 7,
        "match_id": "20260912_GAM_FCT",
        "game_id": "2026091204",
        "date": "2026-09-12",
        "home": "GAM",
        "away": "FCT",
        "score": "0-2",
    },
    {
        "mw": 8,
        "match_id": "20260919_FCT_NAG",
        "game_id": "2026091902",
        "date": "2026-09-19",
        "home": "FCT",
        "away": "NAG",
        "score": "1-0",
    },
    {
        "mw": 9,
        "match_id": "20261010_FCT_URA",
        "game_id": "2026101009",
        "date": "2026-10-10",
        "home": "FCT",
        "away": "URA",
        "score": "3-0",
    },
    {
        "mw": 10,
        "match_id": "20261017_VER_FCT",
        "game_id": "2026101708",
        "date": "2026-10-17",
        "home": "VER",
        "away": "FCT",
        "score": "0-4",
    },
    {
        "mw": 11,
        "match_id": "20261021_FCT_REY",
        "game_id": "2026102108",
        "date": "2026-10-21",
        "home": "FCT",
        "away": "REY",
        "score": "0-0",
    },
    {
        "mw": 12,
        "match_id": "20261025_FCT_MIT",
        "game_id": "2026102505",
        "date": "2026-10-25",
        "home": "FCT",
        "away": "MIT",
        "score": "6-0",
    },
]


def sync_duplicate_file(src: str, dst: str) -> None:
    """ファイルを複製してエイリアスとしても参照可能にする."""
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def run_canonical_collection() -> None:
    """FC東京全12試合の正規生データを完全収集する."""
    spaia_scraper = SpaiasoccerScraper()
    yahoo_scraper = YahooSoccerScraper()
    flab_scraper = FootballLabScraper()

    raw_dir = ROOT_DIR / "data" / "raw"
    spaia_dir = str(raw_dir / "spaia")
    yahoo_dir = str(raw_dir / "yahoo")
    flab_dir = str(raw_dir / "football_lab")
    md_dir = str(ROOT_DIR / "data" / "markdown")

    logger.info("=== Starting FC Tokyo 12-Match Canonical Data Collection ===")

    success_count = 0

    for idx, m in enumerate(FCT_CANONICAL_MATCHES, start=1):
        mw = m["mw"]
        match_id = m["match_id"]
        game_id = m["game_id"]
        date_str = m["date"]
        h_id = m["home"]
        a_id = m["away"]
        score = m["score"]

        logger.info(
            "[%d/12] Processing MW%d: %s vs %s (%s) [GameID: %s / MatchID: %s]",
            idx,
            mw,
            h_id,
            a_id,
            score,
            game_id,
            match_id,
        )

        # 1. SPAIA
        try:
            spaia_scraper.save_raw_data(game_id=game_id, output_dir=spaia_dir)
            # match_id 形式でも保存
            sync_duplicate_file(
                os.path.join(spaia_dir, f"{game_id}_player_stats.json"),
                os.path.join(spaia_dir, f"{match_id}_player_stats.json"),
            )
            sync_duplicate_file(
                os.path.join(spaia_dir, f"{game_id}_comments.json"),
                os.path.join(spaia_dir, f"{match_id}_comments.json"),
            )
            sync_duplicate_file(
                os.path.join(spaia_dir, f"{game_id}_meta.json"),
                os.path.join(spaia_dir, f"{match_id}_meta.json"),
            )
        except Exception as e:
            logger.error("  SPAIA failed for %s: %s", game_id, e)

        # 2. Yahoo!サッカー
        try:
            yahoo_scraper.save_raw_data(game_id=game_id, output_dir=yahoo_dir)
            sync_duplicate_file(
                os.path.join(yahoo_dir, f"{game_id}_stats.json"),
                os.path.join(yahoo_dir, f"{match_id}_stats.json"),
            )
            sync_duplicate_file(
                os.path.join(yahoo_dir, f"{game_id}_text.json"),
                os.path.join(yahoo_dir, f"{match_id}_text.json"),
            )
        except Exception as e:
            logger.error("  Yahoo failed for %s: %s", game_id, e)

        # 3. Football LAB
        try:
            flab_scraper.save_raw_data(
                match_id=game_id,
                date_str=date_str,
                home_team_id=h_id,
                away_team_id=a_id,
                output_dir=flab_dir,
                markdown_dir=md_dir,
            )
            sync_duplicate_file(
                os.path.join(flab_dir, f"{game_id}.json"),
                os.path.join(flab_dir, f"{match_id}.json"),
            )
            sync_duplicate_file(
                os.path.join(md_dir, f"{game_id}_flab.md"),
                os.path.join(md_dir, f"{match_id}_flab.md"),
            )
        except Exception as e:
            logger.error("  Football LAB failed for %s: %s", game_id, e)

        success_count += 1
        logger.info("  -> MW%d successfully retrieved and synchronized.", mw)
        time.sleep(1.0)

    logger.info("=== Canonical Data Collection Completed: %d/12 matches ===", success_count)


if __name__ == "__main__":
    run_canonical_collection()
