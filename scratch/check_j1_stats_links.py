import sys
import urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/j1/stats/"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html, 'html.parser')

for a in soup.find_all('a'):
    href = a.get('href', '')
    if '/stats/' in href:
        print(f"{a.get_text(strip=True)} -> {href}")
