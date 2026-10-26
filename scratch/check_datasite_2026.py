import urllib.request
import re

for year in [2026, 2025]:
    url = f"https://data.j-league.or.jp/SFMS01/search?competition_years={year}&competition_frame_ids=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            html = res.read().decode("utf-8", errors="ignore")
            matches = re.findall(r"href=['\"](/SFMS02/\?match_card_id=\d+)['\"]", html)
            print(f"Year {year}: HTML len={len(html)}, matches count={len(matches)}")
            if matches:
                print(f"  Sample match: {matches[0]}")
    except Exception as e:
        print(f"Year {year} error: {e}")
