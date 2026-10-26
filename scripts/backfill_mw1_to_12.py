"""
Batch backfill pipeline script (scripts/backfill_mw1_to_12.py).
Backfills initial matchweeks (e.g. MW 1 to 12) from raw markdown or scrapers into SQLite and ChromaDB.
"""

import os
import sys
import glob
import argparse
from pathlib import Path

# Add project root to sys.path so scripts can be run directly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import List, Optional, Dict, Any

from pipeline.db import DEFAULT_DB_PATH
from pipeline.indexer import MatchIndexer
from pipeline.vector_indexer import TacticalVectorIndexer, DEFAULT_CHROMA_DIR
from pipeline.importer import parse_jleague_markdown
from pipeline.normalizer import EntityNormalizer


class BackfillPipeline:
    """Manages bulk ingestion and vectorization for early-season matches."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        chroma_dir: Optional[str] = None,
        indexer: Optional[MatchIndexer] = None,
        vector_indexer: Optional[TacticalVectorIndexer] = None,
        schedule_map: Optional[Dict[str, int]] = None,
    ):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.chroma_dir = chroma_dir or DEFAULT_CHROMA_DIR
        self.normalizer = EntityNormalizer()
        self.schedule_map = schedule_map or {}

        if indexer is not None:
            self.indexer = indexer
            self._owns_indexer = False
        else:
            self.indexer = MatchIndexer(db_path=self.db_path)
            self._owns_indexer = True

        if vector_indexer is not None:
            self.vector_indexer = vector_indexer
        else:
            self.vector_indexer = TacticalVectorIndexer(persist_directory=self.chroma_dir)

    def close(self) -> None:
        """Close database connection if owned."""
        if self._owns_indexer and self.indexer:
            self.indexer.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def run_backfill(
        self,
        data_dir: str,
        start_mw: int = 1,
        end_mw: int = 12,
        pattern: str = "*.md",
    ) -> Dict[str, Any]:
        """
        Scan directory for match files within [start_mw, end_mw], parse,
        and atomically upsert them into SQLite and ChromaDB.
        """
        target_path = Path(data_dir)
        if not target_path.exists():
            return {
                "total_files": 0,
                "processed": 0,
                "skipped": 0,
                "matches": [],
            }

        files = sorted(glob.glob(str(target_path / pattern)))
        processed_matches = []
        skipped_count = 0

        for file_path in files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                bundle = parse_jleague_markdown(content, self.normalizer)
                mw = bundle.match.matchweek
                if mw is None and bundle.match.match_id in self.schedule_map:
                    mw = self.schedule_map[bundle.match.match_id]
                    bundle.match.matchweek = mw

                # Filter by matchweek if present, or include if unassigned/within range
                if mw is not None and (mw < start_mw or mw > end_mw):
                    skipped_count += 1
                    continue

                # Stage 2 for historical confirmed backfill
                bundle.match.source_updated_stage = 2

                # 1. SQLite Upsert
                self.indexer.upsert_bundle(bundle)

                # 2. ChromaDB Upsert (4 chunks per match)
                chunks = self.vector_indexer.upsert_bundle(bundle)

                processed_matches.append(
                    {
                        "match_id": bundle.match.match_id,
                        "matchweek": bundle.match.matchweek,
                        "date": bundle.match.date,
                        "home_team": bundle.match.home_team_id,
                        "away_team": bundle.match.away_team_id,
                        "score": f"{bundle.match.home_score}-{bundle.match.away_score}",
                        "chunks_indexed": len(chunks),
                    },
                )
            except Exception as e:
                # Log error and continue with next match
                print(f"Error processing {file_path}: {e}")
                skipped_count += 1

        return {
            "total_files": len(files),
            "processed": len(processed_matches),
            "skipped": skipped_count,
            "matches": processed_matches,
        }


def main():
    """CLI entrypoint for executing backfill."""
    parser = argparse.ArgumentParser(description="J-League Historical Matches Backfill Pipeline")
    parser.add_argument(
        "--start-mw",
        type=int,
        default=1,
        help="Start matchweek (default: 1)",
    )
    parser.add_argument(
        "--end-mw",
        type=int,
        default=12,
        help="End matchweek (default: 12)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/markdown",
        help="Directory containing markdown match records",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )
    parser.add_argument(
        "--chroma-dir",
        type=str,
        default=DEFAULT_CHROMA_DIR,
        help="ChromaDB storage directory",
    )

    args = parser.parse_args()

    print(f"Starting initial backfill for MW {args.start_mw} to {args.end_mw} from {args.data_dir}...")
    schedule_map = {}
    try:
        from scrapers.schedule_crawler import ScheduleCrawler
        crawler = ScheduleCrawler()
        matches = crawler.build_schedule(start_mw=args.start_mw, end_mw=args.end_mw)
        schedule_map = {m["match_id"]: m["matchweek"] for m in matches if m["matchweek"] is not None}
        print(f"Loaded schedule mapping for {len(schedule_map)} matches.")
    except Exception as e:
        print(f"Warning: Could not load dynamic schedule map: {e}")

    pipeline = BackfillPipeline(
        db_path=args.db_path,
        chroma_dir=args.chroma_dir,
        schedule_map=schedule_map,
    )

    try:
        report = pipeline.run_backfill(
            data_dir=args.data_dir,
            start_mw=args.start_mw,
            end_mw=args.end_mw,
        )
        print(f"Backfill Completed! Processed: {report['processed']}, Skipped: {report['skipped']}")
        for m in report["matches"]:
            print(f" - [{m['match_id']}] MW{m['matchweek'] or '-'}: {m['home_team']} {m['score']} {m['away_team']}")
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
