import urllib.request
from bs4 import BeautifulSoup
import re
import json

url = "https://data.j-league.or.jp/SFMS01/search?competition_years=2024&competition_frame_ids=1"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as res:
    html = res.read().decode("utf-8", errors="ignore")

soup = BeautifulSoup(html, "html.parser")
table = soup.find("table")
rows = table.find_all("tr") if table else []

parsed_matches = []
for r in rows:
    cols = [td.get_text(strip=True) for td in r.find_all(["td", "th"])]
    link = r.find("a", href=re.compile(r"/SFMS02/"))
    if link and len(cols) >= 8:
        href = link.get("href", "")
        m_id_match = re.search(r"match_card_id=(\d+)", href)
        card_id = m_id_match.group(1) if m_id_match else ""
        
        # cols: [year, league, sec, date, time, home, score, away, stadium, attendance, broadcast]
        sec_str = cols[2] # e.g. 第１節第１日
        m_sec = re.search(r"第(\d+)節", sec_str)
        sec_num = int(m_sec.group(1)) if m_sec else 0
        
        parsed_matches.append({
            "season": cols[0],
            "competition": cols[1],
            "section_raw": cols[2],
            "matchweek": sec_num,
            "date_raw": cols[3],
            "time": cols[4],
            "home_team": cols[5],
            "score": cols[6],
            "away_team": cols[7],
            "stadium": cols[8] if len(cols) > 8 else "",
            "attendance": cols[9] if len(cols) > 9 else "",
            "card_id": card_id,
        })

print(f"Total parsed matches: {len(parsed_matches)}")
mw1_to_12 = [m for m in parsed_matches if 1 <= m["matchweek"] <= 12]
print(f"Matches in MW 1-12: {len(mw1_to_12)}")
with open("scratch/sample_mw1_12.json", "w", encoding="utf-8") as f:
    json.dump(mw1_to_12[:10], f, ensure_ascii=False, indent=2)
print("Saved sample 10 matches to scratch/sample_mw1_12.json")
