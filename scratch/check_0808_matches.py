import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

headers = {'User-Agent': 'Mozilla/5.0'}

print("Checking 2026-08-08 URLs on jleague.jp:")
for idx in range(1, 15):
    url = f"https://www.jleague.jp/match/j1/2026/0808{idx:02d}/"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')
            h1 = soup.find('h1')
            h1_text = h1.get_text(strip=True) if h1 else 'No H1'
            print(f"  {idx:02d}: {url} -> {h1_text}")
    except Exception as e:
        # 404 or other
        pass
