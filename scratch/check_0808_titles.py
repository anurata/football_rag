import urllib.request
from bs4 import BeautifulSoup

results = []
for i in range(1, 10):
    url = f"https://www.jleague.jp/match/j1/2026/0808{i:02d}/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            html = res.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            h1 = soup.find("h1")
            title = soup.find("title")
            t_text = h1.get_text(strip=True) if h1 else (title.get_text(strip=True) if title else "No title")
            results.append(f"0808{i:02d}: {t_text}")
    except Exception as e:
        results.append(f"0808{i:02d}: Error {e}")

with open("scratch/0808_titles.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(results))
print("Saved scratch/0808_titles.txt")
