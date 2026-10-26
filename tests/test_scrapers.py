"""
Integration test for newly organized scrapers package.
"""

import os
import unittest
from bs4 import BeautifulSoup
from scrapers.jleague_official import extract_match_title, extract_basic_info
from scrapers.football_lab import extract_flab_report_text
from scrapers.fctokyo_official import extract_fctokyo_title


class TestScrapersPackage(unittest.TestCase):
    """Ensure modules inside scrapers/ package are accessible and functional."""

    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        match_html = os.path.join(base_dir, "page_match.html")
        flab_html = os.path.join(base_dir, "page_flab_report.html")
        fctokyo_html = os.path.join(base_dir, "page_fctokyo.html")

        with open(match_html, "r", encoding="utf-8") as f:
            cls.jleague_soup = BeautifulSoup(f.read(), "html.parser")

        with open(flab_html, "r", encoding="utf-8") as f:
            cls.flab_soup = BeautifulSoup(f.read(), "html.parser")

        with open(fctokyo_html, "r", encoding="utf-8") as f:
            cls.fctokyo_soup = BeautifulSoup(f.read(), "html.parser")

    def test_jleague_scraper_package_import(self):
        """Test jleague_official scraper extraction via scrapers package."""
        title = extract_match_title(self.jleague_soup, "test_id")
        self.assertIn("ＦＣ東京", title)
        info = extract_basic_info(self.jleague_soup)
        self.assertEqual(info["stadium"], "味の素スタジアム")

    def test_football_lab_package_import(self):
        """Test football_lab scraper extraction via scrapers package."""
        report = extract_flab_report_text(self.flab_soup)
        self.assertTrue(len(report) > 0)

    def test_fctokyo_package_import(self):
        """Test fctokyo_official scraper extraction via scrapers package."""
        title = extract_fctokyo_title(self.fctokyo_soup)
        self.assertIn("MATCH REVIEW & INTERVIEW", title)


if __name__ == "__main__":
    unittest.main()
