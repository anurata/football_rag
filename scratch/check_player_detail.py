import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# アシストランキングページから選手リンクを取得して選手詳細ページを見る
url = "https://www.jleague.jp/j1/stats/player/2026-27/assist/search-list/"
headers = {'User-Agent': 'Mozilla/5.0'}
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')
    
    player_links = soup.find_all('a', href=lambda h: h and '/player/' in h)
    print(f"Player links found: {len(player_links)}")
    for a in player_links[:5]:
        print(f"  {a.get_text(strip=True)} -> {a.get('href')}")
    
    if player_links:
        target_url = "https://www.jleague.jp" + player_links[0]['href']
        req2 = urllib.request.Request(target_url, headers=headers)
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            soup2 = BeautifulSoup(resp2.read().decode('utf-8', errors='ignore'), 'html.parser')
        print(f"\nPlayer Page Title: {soup2.title.get_text() if soup2.title else ''}")
        for h in soup2.find_all(['h2', 'h3', 'dt', 'th']):
            txt = h.get_text(strip=True)
            if any(k in txt for k in ['タックル', 'ブロック', '奪取', 'カット', 'インターセプト', 'アシスト', 'スタッツ']):
                print(f"  [{h.name}] {txt}")
except Exception as e:
    print("Error:", e)
