import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

urls = [
    "https://www.jleague.jp/match/search/j1/2026/",
    "https://www.jleague.jp/match/section/j1/2026/",
    "https://www.jleague.jp/match/search/j1/2024/",
    "https://www.jleague.jp/match/section/j1/1/",
]

headers = {'User-Agent': 'Mozilla/5.0'}
for u in urls:
    try:
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')
            print(f"URL: {u} -> Status: 200, Title: {soup.title.get_text()[:60] if soup.title else 'No title'}")
            # matchリンクがあるか
            links = [a.get('href') for a in soup.find_all('a') if a.get('href') and '/match/j1/' in a.get('href')]
            print(f"  Match links count: {len(links)}")
            if links:
                print(f"  Sample links: {links[:3]}")
    except Exception as e:
        print(f"URL: {u} -> Error: {e}")
