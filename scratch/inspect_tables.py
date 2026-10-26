import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://www.jleague.jp/match/j1/2024/022301/player/'
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')

tables = soup.find_all('table')
print(f'Tables count: {len(tables)}')
for i, t in enumerate(tables):
    cls = t.get('class')
    print(f'Table {i}: class={cls} text_len={len(t.get_text())}')
    headers = [th.get_text(strip=True) for th in t.find_all(['th', 'td'])][:15]
    print(f'  First cells: {headers}')
