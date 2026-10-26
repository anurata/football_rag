import sys
import urllib.request
import re
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/match/search/j1/2026/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html, 'html.parser')

print("Select elements:")
for sel in soup.find_all('select'):
    print(f"  select name={sel.get('name')} id={sel.get('id')}")
    for opt in sel.find_all('option')[:10]:
        print(f"    {opt.get('value')} -> {opt.get_text(strip=True)}")

# URLリンクで search または section を含むものを探す
print("\nLinks containing /match/:")
seen = set()
for a in soup.find_all('a', href=re.compile(r'/match/')):
    href = a.get('href')
    if href not in seen:
        seen.add(href)
        print(f"  {a.get_text(strip=True)[:30]} -> {href}")
