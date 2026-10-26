import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# Jリーグ公式サイトのスタッツランキング
url = "https://www.jleague.jp/stats/j1/2024/"
headers = {'User-Agent': 'Mozilla/5.0'}
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')
    print("Stats page title:", soup.title.get_text() if soup.title else "")
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if 'stat' in href or 'ranking' in href:
            txt = a.get_text(strip=True)
            if txt:
                print(f"  {txt} -> {href}")
except Exception as e:
    print("Error:", e)
