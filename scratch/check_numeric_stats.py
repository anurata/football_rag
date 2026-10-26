import sys
import urllib.request
import re
import json

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/player/1624851/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# 数字が入っているブロックを探す（例: assist や goal や stats）
blocks = re.findall(r'(\{[^{}]*"assist"\s*:\s*\d+[^{}]*\})', html)
print(f"Blocks with assist number: {len(blocks)}")
for b in blocks[:5]:
    print("  ", b)

# さらに守備スタッツの数値ブロック
blocks2 = re.findall(r'(\{[^{}]*(?:tackle|intercept|block|recovery)[^{}]*:\s*\d+[^{}]*\})', html)
print(f"Blocks with def stats number: {len(blocks2)}")
for b in blocks2[:5]:
    print("  ", b)
