import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# J.League Data Site の試合詳細ページURLの例
# 例: 2024年の第1節
url = "https://data.j-league.or.jp/SFMS02/?match_card_id=29571"
headers = {'User-Agent': 'Mozilla/5.0'}
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
        print("Data site match title:", soup.title.get_text() if soup.title else "No title")
        tables = soup.find_all('table')
        print(f"Data site tables count: {len(tables)}")
        for i, t in enumerate(tables):
            text = ' '.join(t.get_text().split())[:80]
            print(f"Table {i}: {text}")
except Exception as e:
    print("Error:", e)
