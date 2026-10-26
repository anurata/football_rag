import sys
import os
import re
import urllib.request
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath('.'))
from pipeline.normalizer import EntityNormalizer

sys.stdout.reconfigure(encoding='utf-8')

normalizer = EntityNormalizer()

def resolve_match_id(url: str):
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')
    
    title_text = soup.title.get_text(strip=True) if soup.title else ""
    if "Ｊ２" in title_text or "Ｊ３" in title_text or "検索" in title_text or "404" in title_text:
        return None, f"Not J1: {title_text[:40]}"
    
    h1 = soup.find('h1')
    h1_text = h1.get_text(strip=True) if h1 else ""
    if "vs" not in h1_text:
        # titleから抽出
        m = re.search(r'【公式】(.+?)\s*vs\s*(.+?)の試合結果', title_text)
        if m:
            home_raw, away_raw = m.group(1).strip(), m.group(2).strip()
        else:
            return None, f"Cannot parse teams from H1/Title: h1='{h1_text}', title='{title_text[:40]}'"
    else:
        parts = h1_text.split("vs")
        home_raw, away_raw = parts[0].strip(), parts[1].strip()

    home_id = normalizer.normalize_team_name(home_raw)
    away_id = normalizer.normalize_team_name(away_raw)
    
    # URLから日付
    m_url = re.search(r'/(\d{4})/(\d{4})\d{2}/', url)
    if m_url:
        date_str = f"{m_url.group(1)}{m_url.group(2)}"
    else:
        date_str = "UNKNOWN"
        
    match_id = f"{date_str}_{home_id}_{away_id}"
    return match_id, f"Valid J1: {home_raw}({home_id}) vs {away_raw}({away_id})"

test_urls = [
    "https://www.jleague.jp/match/j1/2026/080801/",
    "https://www.jleague.jp/match/j1/2026/080802/",
    "https://www.jleague.jp/match/j1/2026/080805/",
    "https://www.jleague.jp/match/j1/2026/080806/",
    "https://www.jleague.jp/match/j1/2026/080807/",
]

for u in test_urls:
    mid, msg = resolve_match_id(u)
    print(f"{u} -> match_id={mid} ({msg})")
