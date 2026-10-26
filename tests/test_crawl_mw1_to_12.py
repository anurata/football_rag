"""
Unit tests for BatchMatchCrawler (tests/test_crawl_mw1_to_12.py).
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.crawl_mw1_to_12 import BatchMatchCrawler
from scrapers.schedule_crawler import ScheduleCrawler


class TestBatchMatchCrawler(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_crawler = MagicMock(spec=ScheduleCrawler)
        self.crawler = BatchMatchCrawler(
            output_dir=self.temp_dir.name,
            crawler=self.mock_crawler,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_is_match_already_crawled_false_when_absent(self):
        self.assertFalse(self.crawler.is_match_already_crawled("20240223_HIR_URA"))

    def test_is_match_already_crawled_true_when_present(self):
        file_path = os.path.join(self.temp_dir.name, "20240223_HIR_URA.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("# Match File Content")

        self.assertTrue(self.crawler.is_match_already_crawled("20240223_HIR_URA"))

    def test_dry_run_does_not_scrape(self):
        self.mock_crawler.build_schedule.return_value = [
            {
                "match_id": "20240223_HIR_URA",
                "matchweek": 1,
                "official_url": "https://example.com/1",
            },
            {
                "match_id": "20240223_NAG_KAS",
                "matchweek": 1,
                "official_url": "https://example.com/2",
            },
        ]

        result = self.crawler.run(start_mw=1, end_mw=1, dry_run=True)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["crawled"], 0)
        self.assertEqual(result["failed"], 0)

    def test_limit_matches(self):
        self.mock_crawler.build_schedule.return_value = [
            {"match_id": f"match_{i}", "matchweek": 1, "official_url": "url"}
            for i in range(10)
        ]

        result = self.crawler.run(start_mw=1, end_mw=1, limit=3, dry_run=True)
        self.assertEqual(result["total"], 3)


if __name__ == "__main__":
    unittest.main()
