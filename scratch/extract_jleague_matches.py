import sys
import urllib.request
import re
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# 2026年の一覧ページから試合リンクと対戦カードを抽出してみる
url = "https://www.jleague.jp/match/search/j1/2026/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html, 'html.parser')

print("Page Title:", soup.title.get_text() if soup.title else "")

# matchリンクを持つブロックを探す
match_cards = []
for a in soup.find_all('a', href=re.compile(r'/match/j1/2026/\d+/')):
    href = a.get('href')
    txt = ' '.join(a.get_text().split())
    if txt and href not in [c[0] for c in match_cards]:
        match_cards.append((href, txt))

print(f"Match links with text count: {len(match_cards)}")
for href, txt in match_cards[:10]:
    print(f"  {href} -> {txt[:60]}")
