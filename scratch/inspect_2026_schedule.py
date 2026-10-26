import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.schedule_crawler import ScheduleCrawler

crawler = ScheduleCrawler()
matches_2026 = crawler.build_schedule(year=2026, start_mw=1, end_mw=12)
print(f"2026 MW 1-12 total matches: {len(matches_2026)}")
if matches_2026:
    for m in matches_2026[:5]:
        print(f"  MW{m['matchweek']}: {m['date']} {m['home_team_id']} vs {m['away_team_id']} (score: {m['score']}) URL: {m['official_url']}")
