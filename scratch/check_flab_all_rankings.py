import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://www.football-lab.jp/summary/player_ranking/j1/?year=2024'
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')

# 全リンクからランキング関連を抽出
for a in soup.find_all('a'):
    href = a.get('href', '')
    if 'player_ranking' in href or 'cbp' in href:
        print(f"{a.get_text(strip=True)} -> {href}")
