import os
import sys
sys.path.insert(0, os.path.abspath('.'))
import glob
from scrapers.schedule_crawler import ScheduleCrawler

c = ScheduleCrawler()
matches = c.build_schedule(year=2026, start_mw=1, end_mw=12)
expected_ids = set(m['match_id'] for m in matches)

existing = set(
    os.path.basename(f)[:-3]
    for f in glob.glob('data/markdown/2026/*.md')
    if not f.endswith('_flab.md') and not f.endswith('_fctokyo.md')
)

diff = expected_ids - existing
print(f"Missing {len(diff)} matches:")
for mid in sorted(diff):
    m = [x for x in matches if x['match_id'] == mid][0]
    print(f"  {mid}: {m['date']} {m['home_team_raw']} vs {m['away_team_raw']}")
