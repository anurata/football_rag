import sys
import urllib.request
import re

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/player/1624851/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# 「守備」や「タックル」などのスタッツ数値を探索
for kw in ['tackle', 'block', 'intercept', 'recovery', 'assist']:
    m = re.findall(rf'"{kw}[^"]*":\s*([^,}}]+)', html)
    print(f"Key '{kw}': {m[:5]}")
