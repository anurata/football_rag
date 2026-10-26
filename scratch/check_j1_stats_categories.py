import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/j1/stats/"
headers = {'User-Agent': 'Mozilla/5.0'}
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
    print("Title:", soup.title.get_text() if soup.title else "")
    for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'th']):
        t = h.get_text(strip=True)
        if t and len(t) < 30:
            print(f"  [{h.name}] {t}")
except Exception as e:
    print("Error:", e)
