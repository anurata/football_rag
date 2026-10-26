import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/j1/stats/player/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    soup = BeautifulSoup(resp.read().decode('utf-8', errors='ignore'), 'html.parser')

for a in soup.find_all('a'):
    href = a.get('href', '')
    if '/search-list/' in href:
        print(f"{a.get_text(strip=True)} -> {href}")
