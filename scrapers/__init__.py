"""
Scrapers package for J-League tactical analysis RAG.
Provides modules to scrape data from:
- J.League official website (jleague_official)
- Football LAB (football_lab)
- FC Tokyo official website (fctokyo_official)
"""

from .jleague_official import scrape_jleague_match
from .football_lab import scrape_football_lab_match
from .fctokyo_official import scrape_fctokyo_match_review
from .schedule_crawler import ScheduleCrawler

__all__ = [
    "scrape_jleague_match",
    "scrape_football_lab_match",
    "scrape_fctokyo_match_review",
    "ScheduleCrawler",
]
