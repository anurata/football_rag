import requests
from bs4 import BeautifulSoup

url = 'https://soccer.yahoo.co.jp/jleague/category/j1/game/2026102502/stats'
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

with open('scratch/yahoo_stats_sample.txt', 'w', encoding='utf-8') as f:
    f.write('=== TABLES ===\n')
    for i, t in enumerate(soup.find_all('table')):
        f.write(f'\n--- Table {i} ---\n')
        for r in t.find_all('tr')[:10]:
            f.write(' | '.join([c.get_text(strip=True) for c in r.find_all(['th', 'td'])]) + '\n')
    
    f.write('\n=== SECTIONS ===\n')
    for sec in soup.find_all(['section', 'div']):
        classes = sec.get('class', [])
        if any('stat' in c.lower() for c in classes):
            f.write(f"Class: {' '.join(classes)}\nText: {sec.get_text(separator=' ', strip=True)[:150]}\n\n")

print('Done')
