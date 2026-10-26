import sys
import urllib.request
import re

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/player/1624851/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

# section-1-defense の周辺を広く抽出
pos = html.find("section-1-defense")
if pos != -1:
    snippet = html[pos-100:pos+3000]
    # バックスラッシュを解除
    snippet_unescaped = snippet.replace('\\"', '"')
    items = re.findall(r'\{[^{}]*"title"[^{}]*\}', snippet_unescaped)
    for it in items:
        print(it)
else:
    print("Not found")
