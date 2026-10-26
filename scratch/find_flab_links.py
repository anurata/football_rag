import urllib.request
from bs4 import BeautifulSoup

url = "https://www.football-lab.jp/fctk/"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode("utf-8", errors="ignore")

soup = BeautifulSoup(html, "html.parser")

with open("scratch/football_lab_links.txt", "w", encoding="utf-8") as out:
    out.write(f"Title: {soup.title.text if soup.title else ''}\n\n")
    
    # 全リンクの調査
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if any(k in href for k in ["match", "report", "stats", "fctk"]):
            out.write(f"{text} -> {href}\n")

print("saved football_lab_links.txt")
