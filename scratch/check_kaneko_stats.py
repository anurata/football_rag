import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# 金子 拓郎選手の詳細ページ
url = "https://www.jleague.jp/player/1624851/"
headers = {'User-Agent': 'Mozilla/5.0'}
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(html, 'html.parser')
    
    print("Page Title:", soup.title.get_text() if soup.title else "")
    # dl / dt / dd や table を探す
    for dl in soup.find_all(['dl', 'tr']):
        txt = ' '.join(dl.get_text().split())
        if any(k in txt for k in ['タックル', 'ブロック', '奪取', 'カット', 'インターセプト', 'アシスト', 'デュエル', 'クリア']):
            print(f"  {txt}")
except Exception as e:
    print("Error:", e)
