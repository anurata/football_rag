# -*- coding: utf-8 -*-
"""
Rebuild all tactical structures deterministically (scripts/rebuild_all_tactical_structures.py).
Replaces generic template descriptions with concrete, match-specific tactical data.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.match_tactical_enricher import DeterministicTacticalEnricher


def main() -> None:
    enricher = DeterministicTacticalEnricher()
    count = enricher.enrich_all_matches()
    print(f"\n[DONE] Successfully re-enriched {count} matches with concrete tactical structures.")


if __name__ == "__main__":
    main()

