import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# J1の2024年の試合詳細
# 例: 2024/02/23 広島vs浦和 の公式記録
# https://data.j-league.or.jp/SFMS01/search?competition_years=2024&competition_frame_ids=1
url = "https://data.j-league.or.jp/SFMS01/search?competition_years=2024&competition_frame_ids=1"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')

links = soup.find_all('a', href=lambda h: h and '/SFMS02/?match_card_id=' in h)
print(f"J1 matches found: {len(links)}")
if links:
    first_link = "https://data.j-league.or.jp" + links[0]['href']
    print(f"Opening first match: {links[0].get_text(strip=True)} -> {first_link}")
    req2 = urllib.request.Request(first_link, headers=headers)
    with urllib.request.urlopen(req2, timeout=10) as resp2:
        soup2 = BeautifulSoup(resp2.read().decode('utf-8', errors='ignore'), 'html.parser')
    
    # 公式記録テーブル
    for t in soup2.find_all('table'):
        txt = ' '.join(t.get_text().split())
        if any(k in txt for k in ['得点', 'アシスト', 'シュート']):
            print("--- Table ---")
            print(txt[:300])
