"""
Matchweek update pipeline script (scripts/update_matchweek.py).
Supports the 2-stage weekly update flow:
  Stage 1 (Match Day 23:00): Flash reports, basic stats, coach/player interviews.
  Stage 2 (Following Tue 12:00): Confirmed tracking (distance/sprints) + Football LAB tactical indices.
Performs atomic upserts to SQLite and synchronized 4-chunk indexing into ChromaDB.
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

from pipeline.db import get_db_connection, DEFAULT_DB_PATH
from pipeline.indexer import MatchIndexer
from pipeline.vector_indexer import TacticalVectorIndexer, DEFAULT_CHROMA_DIR
from pipeline.importer import parse_jleague_markdown
from pipeline.models import MatchBundleModel
from pipeline.normalizer import EntityNormalizer


class MatchweekUpdater:
    """Orchestrates Stage 1 & Stage 2 transactional updates across SQLite and ChromaDB."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        chroma_dir: Optional[str] = None,
        indexer: Optional[MatchIndexer] = None,
        vector_indexer: Optional[TacticalVectorIndexer] = None,
    ):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.chroma_dir = chroma_dir or DEFAULT_CHROMA_DIR
        self.normalizer = EntityNormalizer()

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
        """Close resources if owned."""
        if self._owns_indexer and self.indexer:
            self.indexer.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def update_match_bundle(
        self,
        bundle: MatchBundleModel,
        stage: int = 1,
    ) -> Dict[str, Any]:
        """
        Atomically persist match bundle into SQLite and ChromaDB with stage tracking.
        """
        bundle.match.source_updated_stage = stage

        # 1. SQLite Upsert
        self.indexer.upsert_bundle(bundle)

        # 2. ChromaDB Vector Indexing (4 chunks per match)
        indexed_chunks = self.vector_indexer.upsert_bundle(bundle)

        return {
            "match_id": bundle.match.match_id,
            "stage": stage,
            "season": bundle.match.season,
            "matchweek": bundle.match.matchweek,
            "home_team": bundle.match.home_team_id,
            "away_team": bundle.match.away_team_id,
            "score": f"{bundle.match.home_score}-{bundle.match.away_score}",
            "team_stats_count": len(bundle.team_stats),
            "player_stats_count": len(bundle.player_stats),
            "events_count": len(bundle.events),
            "reviews_count": len(bundle.reviews),
            "chunks_indexed": len(indexed_chunks),
        }

    def update_from_markdown_file(
        self,
        file_path: str,
        stage: int = 1,
    ) -> Dict[str, Any]:
        """Read a match report Markdown file and execute the update pipeline."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(p, "r", encoding="utf-8") as f:
            content = f.read()

        bundle = parse_jleague_markdown(content, self.normalizer)
        return self.update_match_bundle(bundle, stage=stage)

    def update_from_directory(
        self,
        directory_path: str,
        stage: int = 1,
        pattern: str = "*.md",
    ) -> List[Dict[str, Any]]:
        """Scan directory and batch process all matching markdown reports."""
        target_dir = Path(directory_path)
        if not target_dir.exists():
            return []

        files = sorted(glob.glob(str(target_dir / pattern)))
        results = []
        for file_path in files:
            res = self.update_from_markdown_file(file_path, stage=stage)
            results.append(res)
        return results


def main():
    """CLI entrypoint for running weekly batch update."""
    parser = argparse.ArgumentParser(description="J-League Matchweek 2-Stage Updater")
    parser.add_argument(
        "--stage",
        type=int,
        choices=[1, 2],
        default=1,
        help="Update stage (1=Match Day Flash, 2=Confirmed Tracking)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/markdown",
        help="Directory containing match markdown files",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Specific markdown file to update",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=DEFAULT_DB_PATH,
        help="Target SQLite database path",
    )
    parser.add_argument(
        "--chroma-dir",
        type=str,
        default=DEFAULT_CHROMA_DIR,
        help="Target ChromaDB persistent storage directory",
    )

    args = parser.parse_args()

    updater = MatchweekUpdater(
        db_path=args.db_path,
        chroma_dir=args.chroma_dir,
    )

    try:
        if args.file:
            print(f"Processing single file (Stage {args.stage}): {args.file}")
            res = updater.update_from_markdown_file(args.file, stage=args.stage)
            print(f"Updated successfully: {res['match_id']} (Chunks: {res['chunks_indexed']})")
        else:
            print(f"Scanning directory (Stage {args.stage}): {args.data_dir}")
            results = updater.update_from_directory(args.data_dir, stage=args.stage)
            print(f"Processed {len(results)} matches.")
            for r in results:
                print(f" - {r['match_id']}: {r['home_team']} {r['score']} {r['away_team']} (Stage {r['stage']})")
    finally:
        updater.close()


if __name__ == "__main__":
    main()
