import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://data.j-league.or.jp/SFMS02/?match_card_id=30430"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')

print("Title:", soup.title.get_text() if soup.title else "")
for i, t in enumerate(soup.find_all('table')):
    txt = ' '.join(t.get_text().split())
    print(f"Table {i} ({len(txt)} chars): {txt[:120]}")
