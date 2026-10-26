import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

# 月別や節別のタブやリンクを探す
url = "https://www.jleague.jp/match/search/j1/2026/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')

# 月別リンク（例: 8月, 9月, 10月）や節別リンク（第1節〜第12節）
for a in soup.find_all('a'):
    href = a.get('href', '')
    txt = a.get_text(strip=True)
    if any(k in txt for k in ['8月', '9月', '10月', '第1節', '第2節', '第3節', '節', '月']):
        print(f"  {txt} -> {href}")
