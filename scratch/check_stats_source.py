import sys
import re
import urllib.request
import json

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://www.jleague.jp/match/j1/2024/022301/player/'
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# intercept_count の周辺の JSON またはテキストを探す
for m in re.finditer(r'intercept_count', html):
    start = max(0, m.start() - 150)
    end = min(len(html), m.end() + 150)
    print("=== Found intercept_count ===")
    print(html[start:end])
    print("-" * 50)
