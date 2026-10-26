import urllib.request
from bs4 import BeautifulSoup

url = "https://www.jleague.jp/match/j1/2024/022301/"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
with urllib.request.urlopen(req) as res:
    html = res.read().decode("utf-8", errors="ignore")

soup = BeautifulSoup(html, "html.parser")
print("Title:", soup.find("title").get_text(strip=True) if soup.find("title") else "No title")

# Check for score, stats, report, comments in the initial html
for h in soup.find_all(["h1", "h2", "h3", "h4"]):
    text = h.get_text(strip=True)
    if any(k in text for k in ["戦評", "レポート", "コメント", "スタッツ"]):
        print("Found section header:", text)

with open("scratch/sample_official_page.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Saved HTML to scratch/sample_official_page.html (size:", len(html), ")")
