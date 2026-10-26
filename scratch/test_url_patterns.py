import sys
import urllib.request
import re
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

test_urls = [
    "https://www.jleague.jp/match/search/j1/202608/",
    "https://www.jleague.jp/match/search/j1/2026/08/",
    "https://www.jleague.jp/match/search/j1/all/202608/",
    "https://www.jleague.jp/j1/match/",
    "https://www.jleague.jp/match/section/j1/1/",
    "https://www.jleague.jp/match/section/j1/2026/1/",
]

headers = {'User-Agent': 'Mozilla/5.0'}
for u in test_urls:
    try:
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')
            # 含まれるmatchリンク
            links = set([a.get('href') for a in soup.find_all('a', href=re.compile(r'/match/j1/2026/\d+/'))])
            print(f"URL: {u} -> Status: 200, Match Links: {len(links)}")
            if links:
                print(f"   Sample: {list(links)[:3]}")
    except Exception as e:
        print(f"URL: {u} -> Error: {e}")
