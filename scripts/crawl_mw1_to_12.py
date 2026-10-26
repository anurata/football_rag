"""
Batch Match Crawler for Matchweeks 1 to 12 (scripts/crawl_mw1_to_12.py).
Fetches schedule and crawls official J-League match reviews into markdown files.
"""

import os
import sys
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from playwright.sync_api import sync_playwright
from scrapers.schedule_crawler import ScheduleCrawler
from scrapers.jleague_official import scrape_jleague_match_page


class BatchMatchCrawler:
    """Orchestrates scheduled batch scraping for matches across matchweeks."""

    def __init__(
        self,
        output_dir: str = "data/markdown",
        crawler: Optional[ScheduleCrawler] = None,
    ):
        self.output_dir = output_dir
        self.crawler = crawler or ScheduleCrawler()
        os.makedirs(self.output_dir, exist_ok=True)

    def is_match_already_crawled(self, match_id: str) -> bool:
        """Check if markdown file already exists."""
        target_path = Path(self.output_dir) / f"{match_id}.md"
        return target_path.exists() and target_path.stat().st_size > 0

    def crawl_match_with_retry(
        self,
        page,
        match: Dict[str, Any],
        max_retries: int = 2,
        interval_sec: float = 1.0,
    ) -> bool:
        """Attempt scraping a single match with retries."""
        match_id = match["match_id"]
        url = match["official_url"]

        for attempt in range(1, max_retries + 1):
            try:
                scrape_jleague_match_page(
                    page=page,
                    match_id=match_id,
                    base_url=url,
                    output_dir=self.output_dir,
                    matchweek=match.get("matchweek"),
                )
                time.sleep(interval_sec)
                return True
            except Exception as e:
                print(f"  [Attempt {attempt}/{max_retries} Failed] {match_id}: {e}")
                if attempt < max_retries:
                    time.sleep(2.0)
        return False

    def run(
        self,
        year: int = 2024,
        start_mw: int = 1,
        end_mw: int = 12,
        limit: Optional[int] = None,
        workers: int = 3,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Execute batch crawling across the specified matchweek range."""
        print(f"=== J1 第{start_mw}節〜第{end_mw}節 試合スケジュール取得開始 (Season: {year}) ===")
        matches = self.crawler.build_schedule(
            year=year,
            start_mw=start_mw,
            end_mw=end_mw,
        )
        print(f"対象試合総数: {len(matches)} 試合")

        if limit is not None and limit > 0:
            matches = matches[:limit]
            print(f"取得件数制限適用: 上位 {len(matches)} 試合を対象とします")

        skipped_count = 0
        to_crawl: List[Dict[str, Any]] = []

        for m in matches:
            if self.is_match_already_crawled(m["match_id"]):
                skipped_count += 1
            else:
                to_crawl.append(m)

        print(f"既存キャッシュ済み: {skipped_count} 件 / 新規クロール対象: {len(to_crawl)} 件")

        if dry_run:
            print("[Dry-run モード] 実際のスクレイピングは実行しません。")
            return {
                "total": len(matches),
                "skipped": skipped_count,
                "crawled": 0,
                "failed": 0,
            }

        if not to_crawl:
            print("新規に取得対象となる試合はありません。すべてキャッシュ済みです。")
            return {
                "total": len(matches),
                "skipped": skipped_count,
                "crawled": 0,
                "failed": 0,
            }

        success_count = 0
        failed_count = 0

        def _worker_task(worker_matches: List[Dict[str, Any]], worker_id: int) -> tuple[int, int]:
            w_success = 0
            w_failed = 0
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={
                        "width": 1280,
                        "height": 800,
                    },
                )
                page = context.new_page()

                for j, match in enumerate(worker_matches, start=1):
                    print(f"[Worker-{worker_id}] ({j}/{len(worker_matches)}) {match['match_id']} (MW {match['matchweek']})")
                    ok = self.crawl_match_with_retry(page=page, match=match)
                    if ok:
                        w_success += 1
                    else:
                        w_failed += 1

                browser.close()
            return w_success, w_failed

        import concurrent.futures
        # Distribute matches across workers
        num_workers = max(1, min(workers, len(to_crawl)))
        chunks = [to_crawl[i::num_workers] for i in range(num_workers)]

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(_worker_task, chunks[w_id], w_id + 1)
                for w_id in range(num_workers)
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    s, f = future.result()
                    success_count += s
                    failed_count += f
                except Exception as exc:
                    print(f"Worker encountered exception: {exc}")

        print("\n=== バッチクロール完了 ===")
        print(f"総対象: {len(matches)} / スキップ: {skipped_count} / 成功: {success_count} / 失敗: {failed_count}")

        return {
            "total": len(matches),
            "skipped": skipped_count,
            "crawled": success_count,
            "failed": failed_count,
        }


def main():
    parser = argparse.ArgumentParser(description="J1 Matchweeks Batch Crawler")
    parser.add_argument("--year", type=int, default=2024, help="Target season year (default: 2024)")
    parser.add_argument("--start-mw", type=int, default=1, help="Start matchweek (default: 1)")
    parser.add_argument("--end-mw", type=int, default=12, help="End matchweek (default: 12)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of matches to crawl")
    parser.add_argument("--workers", type=int, default=3, help="Number of parallel workers (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Print targets without downloading")
    parser.add_argument("--output-dir", type=str, default="data/markdown", help="Output directory")

    args = parser.parse_args()

    crawler = BatchMatchCrawler(output_dir=args.output_dir)
    crawler.run(
        year=args.year,
        start_mw=args.start_mw,
        end_mw=args.end_mw,
        limit=args.limit,
        workers=args.workers,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
