"""
2026 Season J1 Match Markdown Crawler (scripts/crawl_2026_matches.py)
Crawls Matchweek 1-12 (120 matches) with self-consistency verification.
"""

import os
import sys
import time
from typing import Dict, List, Set
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.abspath("."))
from pipeline.normalizer import EntityNormalizer
from scrapers.jleague_official import scrape_jleague_match_page
from scrapers.schedule_crawler import ScheduleCrawler


def get_existing_valid_matches(output_dir: str) -> Set[str]:
    """すでに正常取得（2KB以上）されているmatch_idのセットを返す。"""
    if not os.path.exists(output_dir):
        return set()

    valid_ids = set()
    for fname in os.listdir(output_dir):
        if fname.endswith(".md") and not fname.endswith("_flab.md") and not fname.endswith("_fctokyo.md"):
            fpath = os.path.join(output_dir, fname)
            if os.path.getsize(fpath) > 2000:
                valid_ids.add(fname[:-3])
    return valid_ids


def run_crawler_2026(
    start_mw: int = 1,
    end_mw: int = 38,
    output_dir: str = "data/markdown/2026",
    max_idx_per_date: int = 25,
) -> None:
    """2026シーズンのJ1全試合データを高精度にスクレイピングする。"""
    normalizer = EntityNormalizer()
    crawler = ScheduleCrawler(normalizer=normalizer)

    print(f"=== 2026シーズン 第{start_mw}節〜第{end_mw}節 スクレイピング開始 ===")
    official_schedule = crawler.build_schedule(
        year=2026,
        start_mw=start_mw,
        end_mw=end_mw,
    )
    total_target = len(official_schedule)
    print(f"目標試合数: {total_target} 試合 (全{len(set(m['date'] for m in official_schedule))} 開催日)")

    # 日付ごとの予定J1カード
    date_schedule: Dict[str, List[dict]] = {}
    for m in official_schedule:
        date_schedule.setdefault(m["date"], []).append(m)

    os.makedirs(output_dir, exist_ok=True)
    existing_ids = get_existing_valid_matches(output_dir)
    print(f"既存取得済み（正常）: {len(existing_ids)} 試合\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={
                "width": 1280,
                "height": 800,
            },
        )
        total_scraped = len(existing_ids)

        for date_str, expected_matches in sorted(date_schedule.items()):
            expected_count = len(expected_matches)
            mmdd = date_str.replace("-", "")[4:]  # '0808'

            # この日付の既存取得数を確認
            date_existing = [
                m["match_id"] for m in expected_matches
                if m["match_id"] in existing_ids
            ]
            if len(date_existing) == expected_count:
                print(f"[{date_str}] 全{expected_count}試合 取得済みのためスキップ。")
                continue

            print(f"--- 開催日: {date_str} (J1予定: {expected_count}試合) ---")
            found_on_date = len(date_existing)
            consecutive_invalid = 0

            for idx in range(1, max_idx_per_date + 1):
                if found_on_date >= expected_count:
                    print(f"  -> {date_str} の全J1試合 ({expected_count}試合) 収集完了。")
                    break

                target_url = f"https://www.jleague.jp/match/j1/2026/{mmdd}{idx:02d}/"
                dummy_id = f"{date_str.replace('-', '')}_{mmdd}{idx:02d}"

                # 各試合ごとにクリーンなPageを開く
                page = context.new_page()
                try:
                    saved_path = scrape_jleague_match_page(
                        page=page,
                        match_id=dummy_id,
                        base_url=target_url,
                        output_dir=output_dir,
                        matchweek=expected_matches[0]["matchweek"],
                        normalizer=normalizer,
                    )
                finally:
                    page.close()

                if saved_path is not None:
                    found_on_date += 1
                    total_scraped += 1
                    print(f"  [進捗] 全体: {total_scraped}/{total_target} 試合完了\n")
                    time.sleep(1.0)
                else:
                    time.sleep(0.3)

        browser.close()

    print(f"\n=== スクレイピング完了: 計 {total_scraped}/{total_target} 試合 ===")


if __name__ == "__main__":
    run_crawler_2026(start_mw=1, end_mw=38)
