import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.football-lab.jp/hiro/report/?year=2024&month=02&date=23"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')

category_names = {
    "1": "攻撃",
    "2": "パス",
    "3": "クロス",
    "4": "ドリブル",
    "5": "シュート",
    "6": "奪取",
    "7": "守備",
    "8": "セーブ",
}

for cat_id, cat_name in category_names.items():
    rank_div = soup.find(id=f"rank{cat_id}")
    if rank_div:
        print(f"=== カテゴリ: {cat_name} (rank{cat_id}) ===")
        tbl = rank_div.find("table")
        if tbl:
            for tr in tbl.find_all("tr")[:6]:
                cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                print("  " + " | ".join(cells))
