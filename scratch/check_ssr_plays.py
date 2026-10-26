import sys
import re
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/match/j1/2024/022301/live/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# 試合中のプレー記述（例: 「シュート」「クロス」「パス」「ゴール」）を探す
patterns = ['シュート', 'ゴール', '奪', 'タックル', 'ブロック', 'アシスト', 'カット']
for p in patterns:
    matches = [m.start() for m in re.finditer(p, html)]
    print(f"Pattern '{p}': {len(matches)} occurrences")
    for pos in matches[:3]:
        snippet = html[max(0, pos-40):min(len(html), pos+60)].replace('\n', ' ')
        print(f"  [{pos}] {snippet}")
