import requests
from bs4 import BeautifulSoup

url = 'https://soccer.yahoo.co.jp/jleague/category/j1/teams'
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

with open('scratch/yahoo_teams.txt', 'w', encoding='utf-8') as f:
    for a in soup.find_all('a', href=True):
        if '/schedule' in a['href']:
            parent = a.find_parent(['li', 'div', 'section', 'tr'])
            txt = parent.get_text(separator=' ', strip=True) if parent else ''
            f.write(f"{a['href']}: {txt}\n")
print('Wrote scratch/yahoo_teams.txt')
