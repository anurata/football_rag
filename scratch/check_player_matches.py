import sys
import urllib.request
import re

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/player/1624851/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# 試合一覧（match list）や節ごとのデータがあるか？
matches_pos = [m.start() for m in re.finditer(r'第\d+節', html)]
print(f"Matchweek mentions: {len(matches_pos)}")
for p in matches_pos[:5]:
    print(html[max(0, p-50):min(len(html), p+100)])
