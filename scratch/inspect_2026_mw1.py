import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from scrapers.schedule_crawler import ScheduleCrawler

sys.stdout.reconfigure(encoding='utf-8')

c = ScheduleCrawler()
matches = c.build_schedule(year=2026, start_mw=1, end_mw=1)

print("2026 Matchweek 1 matches from Data Site:")
for m in matches:
    print(f"  {m['date']} {m['time']} {m['home_team_raw']} vs {m['away_team_raw']} (stadium: {m['stadium']})")
