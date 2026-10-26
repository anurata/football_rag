from bs4 import BeautifulSoup
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scrapers.jleague_official import (
    extract_match_title,
    extract_basic_info,
    extract_team_stats,
    extract_match_report,
    extract_comments,
    build_markdown_content,
)

with open("scratch/sample_official_page.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
title = extract_match_title(soup, "20240223_HIR_URA")
info = extract_basic_info(soup)
stats = extract_team_stats(soup)
report = extract_match_report(soup)
coach = extract_comments(soup, "監督コメント")
player = extract_comments(soup, "選手コメント")

print(f"Title: {title}")
print(f"Info: {info}")
print(f"Stats items count: {len(stats)}")
print(f"Report length: {len(report)}")
print(f"Coach comments count: {len(coach)}")
print(f"Player comments count: {len(player)}")
