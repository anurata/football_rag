import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# Football LAB の選手ランキングページURLを試す
urls = [
    "https://www.football-lab.jp/summary/player_ranking/j1/",
    "https://www.football-lab.jp/ranking/player/",
]

headers = {'User-Agent': 'Mozilla/5.0'}
for u in urls:
    try:
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            print(f"URL: {u} -> Status: {resp.status}, Title: {soup.title.get_text() if soup.title else 'No title'}")
    except Exception as e:
        print(f"URL: {u} -> Error: {e}")
