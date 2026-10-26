import urllib.request
from bs4 import BeautifulSoup
import re

for i in range(1, 10):
    url = f"https://www.jleague.jp/match/j1/2026/0808{i:02d}/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            html = res.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            title = soup.find("title")
            t_text = title.get_text(strip=True) if title else "No title"
            print(f"0808{i:02d} -> {t_text}")
    except Exception as e:
        print(f"0808{i:02d} -> Error: {e}")
