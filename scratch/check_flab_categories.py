import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://www.football-lab.jp/summary/player_ranking/j1/'
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')

links = soup.find_all('a', href=lambda h: h and '/summary/player_ranking/j1/' in h)
seen = set()
for a in links:
    href = a.get('href')
    text = a.get_text(strip=True)
    if href not in seen and text:
        seen.add(href)
        print(f"{text}: {href}")
