"""
Batch Enrichment Script for FC Tokyo 2026 Matches (scripts/enrich_fct_tactics_batch.py).

Enriches MW1 to MW11 matches with high-fidelity tactical structures using Gemini 3.8 Flash,
while strictly preserving MW12 (Mito) ground truth.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.fetch_fct_canonical import FCT_CANONICAL_MATCHES
from pipeline.tactical_enricher import TacticalEnricher
from agent.gemini_client import GeminiTacticalClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("enrich_fct_batch")


def run_batch_enrichment(start_mw: int = 1, end_mw: int = 11) -> None:
    """Run tactical enrichment batch for specified matchweeks."""
    client = GeminiTacticalClient()
    if not client.is_available():
        logger.error("Gemini API client is not available. Please check GEMINI_API_KEY.")
        sys.exit(1)

    enricher = TacticalEnricher(gemini_client=client)

    logger.info("Starting high-fidelity tactical enrichment for MW%d to MW%d...", start_mw, end_mw)

    for m in FCT_CANONICAL_MATCHES:
        mw = m["mw"]
        if mw < start_mw or mw > end_mw:
            continue

        game_id = m["game_id"]
        match_id = m["match_id"]
        score = m["score"]

        # Preserve MW12 Mito
        if mw == 12 or game_id == "2026102505":
            logger.info("MW12 (FC Tokyo vs Mito: %s) is protected ground truth. Skipping.", game_id)
            continue

        logger.info("Processing MW%d (%s: %s, Score: %s)...", mw, match_id, game_id, score)

        success = False
        for attempt in range(1, 3):
            try:
                res = enricher.extract_tactical_structure(
                    target_id=game_id,
                    match_id_synonym=match_id,
                )
                highlights = res.get("tactical_highlights", [])
                phases = res.get("phases", [])
                logger.info(
                    "MW%d SUCCESS: %d highlights, %d phases generated.",
                    mw,
                    len(highlights),
                    len(phases),
                )
                success = True
                break
            except Exception as e:
                logger.warning("Attempt %d failed for MW%d (%s): %s", attempt, mw, game_id, e)
                time.sleep(3)

        if not success:
            logger.error("Failed to enrich MW%d (%s) after retries.", mw, game_id)

        # Rate limit pause
        time.sleep(2)

    logger.info("Batch enrichment process finished.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1, help="Start Matchweek")
    parser.add_argument("--end", type=int, default=11, help="End Matchweek")
    args = parser.parse_args()

    run_batch_enrichment(start_mw=args.start, end_mw=args.end)
