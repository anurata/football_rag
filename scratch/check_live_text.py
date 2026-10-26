import sys
import re
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/match/j1/2024/022301/live/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

soup = BeautifulSoup(html, 'html.parser')

# テキスト速報のイベントブロックを抽出
events = []
# 一般的なテキスト速報クラスを探す
for div in soup.find_all(class_=lambda c: c and ('live' in c or 'timeline' in c or 'comment' in c or 'event' in c)):
    txt = div.get_text(strip=True)
    if any(k in txt for k in ['アシスト', 'タックル', 'ブロック', '奪取', 'カット']):
        events.append((div.get('class'), txt[:120]))

print(f"Events found: {len(events)}")
for cls, txt in events[:10]:
    print(f"Class: {cls} -> {txt}")
