import urllib.request
from bs4 import BeautifulSoup
import re

url = "https://www.jleague.jp/match/section/j1/1/"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
try:
    with urllib.request.urlopen(req, timeout=10) as res:
        html = res.read().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        print("Page title:", soup.find("title").get_text(strip=True) if soup.find("title") else "")
        # Find all match links
        links = soup.find_all("a", href=re.compile(r"/match/j1/2026/\d+/"))
        print("Found match links:", len(links))
        for a in links:
            print("  Link:", a.get("href"), "Text:", a.get_text(" ", strip=True)[:60])
except Exception as e:
    print("Error:", e)
