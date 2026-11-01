# -*- coding: utf-8 -*-
"""
Scheduled Pipeline Runner (scripts/run_scheduled_pipeline.py).
Executes KO-relative pending phases (Preview Draft, Preview Final, Stage 1, Stage 2)
idempotently based on schedule and match state.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pipeline.db import DEFAULT_DB_PATH
from pipeline.phase_calculator import (
    JST,
    PREVIEW_DRAFT,
    PREVIEW_FINAL,
    STAGE1,
    STAGE2,
    plan_matches,
)
from pipeline.preview_fact_extractor import PreviewFactExtractor
from pipeline.preview_markdown_formatter import format_preview_markdown
from scrapers.schedule_crawler import ScheduleCrawler
from scripts.plan_phases import build_done_lookup, load_stage_map
from scripts.update_matchweek import MatchweekUpdater

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scheduled_pipeline")


class ScheduledPipelineRunner:
    """Executes planned phases for upcoming and concluded matches."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        exports_dir: Optional[Path] = None,
        markdown_dir: Optional[Path] = None,
        dry_run: bool = False,
    ) -> None:
        self.db_path = str(db_path)
        self.exports_dir = exports_dir or (ROOT_DIR / "exports")
        self.markdown_dir = markdown_dir or (ROOT_DIR / "data" / "markdown" / "2026")
        self.dry_run = dry_run
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def run_preview_draft(self, match: Dict[str, Any]) -> bool:
        """Generates draft preview facts and formatted markdown (_auto.md)."""
        match_id = match.get("match_id", "")
        home = match.get("home", "")
        away = match.get("away", "")
        date_str = match.get("kickoff", "")[:10]
        mw = int(match.get("matchweek", 0))

        logger.info(f"[{match_id}] Generating Preview Draft (Auto)...")
        if self.dry_run:
            logger.info(f"[{match_id}] [DRY-RUN] Preview Draft skipped.")
            return True

        try:
            extractor = PreviewFactExtractor(db_path=self.db_path)
            facts = extractor.extract_match_preview_facts(
                home_team_id=home,
                away_team_id=away,
                match_date=date_str,
                matchweek=mw,
            )
            report_md = format_preview_markdown(facts)
            out_file = self.exports_dir / f"{match_id}_preview_auto.md"
            out_file.write_text(report_md, encoding="utf-8")
            logger.info(f"[{match_id}] Preview Draft saved -> {out_file.name}")
            return True
        except Exception as e:
            logger.error(f"[{match_id}] Failed to generate preview draft: {e}", exc_info=True)
            return False

    def run_preview_final(self, match: Dict[str, Any]) -> bool:
        """Prepares KO-24h export for NotebookLM."""
        match_id = match.get("match_id", "")
        logger.info(f"[{match_id}] Generating Preview Final (NotebookLM)...")
        if self.dry_run:
            logger.info(f"[{match_id}] [DRY-RUN] Preview Final skipped.")
            return True

        try:
            notebooklm_dir = self.exports_dir / "notebooklm"
            notebooklm_dir.mkdir(parents=True, exist_ok=True)
            out_file = notebooklm_dir / f"{match_id}_notebooklm.md"

            # Auto draftがあればそれを元に生成、なければ直接抽出
            auto_draft = self.exports_dir / f"{match_id}_preview_auto.md"
            if auto_draft.exists():
                content = auto_draft.read_text(encoding="utf-8")
            else:
                extractor = PreviewFactExtractor(db_path=self.db_path)
                facts = extractor.extract_match_preview_facts(
                    home_team_id=match.get("home", ""),
                    away_team_id=match.get("away", ""),
                    match_date=match.get("kickoff", "")[:10],
                    matchweek=int(match.get("matchweek", 0)),
                )
                content = format_preview_markdown(facts)

            header = (
                f"# NotebookLM Ingestion Document - {match_id}\n"
                f"Generated: {datetime.now(JST).isoformat()}\n\n"
            )
            out_file.write_text(header + content, encoding="utf-8")
            logger.info(f"[{match_id}] Preview Final saved -> {out_file.name}")
            return True
        except Exception as e:
            logger.error(f"[{match_id}] Failed to generate preview final: {e}", exc_info=True)
            return False

    def run_stage(self, match: Dict[str, Any], stage: int) -> bool:
        """Executes Stage 1 or Stage 2 update using MatchweekUpdater."""
        match_id = match.get("match_id", "")
        logger.info(f"[{match_id}] Executing Stage {stage} pipeline...")
        if self.dry_run:
            logger.info(f"[{match_id}] [DRY-RUN] Stage {stage} skipped.")
            return True

        try:
            target_file = self.markdown_dir / f"{match_id}.md"
            updater = MatchweekUpdater(db_path=self.db_path)
            try:
                if target_file.exists():
                    updater.update_from_markdown_file(str(target_file), stage=stage)
                    logger.info(f"[{match_id}] Stage {stage} updated from {target_file.name}")
                else:
                    logger.warning(
                        f"[{match_id}] Markdown {target_file.name} not found. "
                        "Checking matchweek directory..."
                    )
                    updater.update_from_directory(str(self.markdown_dir), stage=stage)
            finally:
                updater.close()
            return True
        except Exception as e:
            logger.error(f"[{match_id}] Failed to execute Stage {stage}: {e}", exc_info=True)
            return False

    def execute_phase(self, match: Dict[str, Any], phase: str) -> bool:
        """Routes a pending phase to its respective executor."""
        if phase == PREVIEW_DRAFT:
            return self.run_preview_draft(match)
        elif phase == PREVIEW_FINAL:
            return self.run_preview_final(match)
        elif phase == STAGE1:
            return self.run_stage(match, stage=1)
        elif phase == STAGE2:
            return self.run_stage(match, stage=2)
        else:
            logger.warning(f"Unknown phase: {phase}")
            return False

    def run_plan(self, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Executes all pending phases in the plan."""
        results: Dict[str, Any] = {
            "total_matches": len(plan),
            "executed": 0,
            "succeeded": 0,
            "failed": 0,
            "details": [],
        }

        for item in plan:
            match_id = item.get("match_id", "")
            phases = item.get("pending_phases", [])
            for phase in phases:
                results["executed"] += 1
                success = self.execute_phase(item, phase)
                if success:
                    results["succeeded"] += 1
                else:
                    results["failed"] += 1
                results["details"].append(
                    {
                        "match_id": match_id,
                        "phase": phase,
                        "success": success,
                    },
                )
        return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scheduled match pipeline.")
    parser.add_argument("--year", type=int, default=2026, help="Season year")
    parser.add_argument("--start-mw", type=int, default=1, help="Start matchweek")
    parser.add_argument("--end-mw", type=int, default=38, help="End matchweek")
    parser.add_argument("--now", type=str, default=None, help="Current time ISO8601 (JST)")
    parser.add_argument("--schedule-html", type=str, default=None, help="HTML file path")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="SQLite DB path")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without side-effects")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now).replace(tzinfo=JST) if args.now else datetime.now(JST)

    html_content = None
    if args.schedule_html:
        html_content = Path(args.schedule_html).read_text(encoding="utf-8")

    crawler = ScheduleCrawler()
    matches = crawler.build_schedule(
        html_content=html_content,
        year=args.year,
        start_mw=args.start_mw,
        end_mw=args.end_mw,
    )

    stage_map = load_stage_map(args.db)
    done_lookup = build_done_lookup(matches, stage_map)
    plan = plan_matches(matches, now, done_lookup)

    logger.info(f"Planning at {now.isoformat()}: {len(plan)} matches pending action.")

    if not plan:
        logger.info("No pending phases. Pipeline finished with zero actions.")
        sys.exit(0)

    runner = ScheduledPipelineRunner(
        db_path=args.db,
        dry_run=args.dry_run,
    )
    summary = runner.run_plan(plan)
    logger.info(f"Execution Summary: {summary}")

    if summary["failed"] > 0:
        logger.error(f"Pipeline completed with {summary['failed']} failures.")
        sys.exit(1)

    logger.info("Pipeline completed successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()

