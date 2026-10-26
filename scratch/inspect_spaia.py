import requests
from bs4 import BeautifulSoup

url = 'https://spaia.jp/soccer/jleague/j1/schedule'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
resp = requests.get(url, headers=headers)
print('Status:', resp.status_code)

soup = BeautifulSoup(resp.text, 'html.parser')
links = []
for a in soup.find_all('a', href=True):
    if '/soccer/' in a['href'] and ('game' in a['href'] or 'match' in a['href'] or 'live' in a['href'] or 'result' in a['href']):
        links.append((a['href'], a.get_text(strip=True)))

print(f'Found {len(links)} match links:')
for href, text in links[:20]:
    print(href, text)
