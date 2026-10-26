import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# 2024年開幕戦のFootball LAB レポート
url = "https://www.football-lab.jp/hiro/report/?year=2024&month=02&date=23"
headers = {'User-Agent': 'Mozilla/5.0'}
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')
    
    # statsTbl6 を探す
    print("=== 全スタッツテーブル項目 ===")
    for tbl in soup.find_all("table", class_=lambda c: c and "statsTbl" in c):
        for tr in tbl.find_all("tr"):
            row = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if any(k in "".join(row) for k in ["タックル", "ブロック", "奪取", "インターセプト", "アシスト", "クリア"]):
                print(" | ".join(row))
except Exception as e:
    print("Error:", e)
