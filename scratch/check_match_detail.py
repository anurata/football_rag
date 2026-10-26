import urllib.request
from bs4 import BeautifulSoup
import re

url = "https://data.j-league.or.jp/SFMS02/?match_card_id=30430"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as res:
    html = res.read().decode("utf-8", errors="ignore")

soup = BeautifulSoup(html, "html.parser")
print("Title:", soup.find("title").get_text(strip=True) if soup.find("title") else "No title")

# Look at tables
tables = soup.find_all("table")
print(f"Total tables: {len(tables)}")
for i, t in enumerate(tables):
    caption = t.find("caption")
    caption_text = caption.get_text(strip=True) if caption else ""
    summary = t.get("summary", "")
    cls = t.get("class", [])
    print(f"Table {i}: class={cls}, caption={caption_text}, summary={summary}")

with open("scratch/sample_match_detail.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Saved HTML to scratch/sample_match_detail.html")
