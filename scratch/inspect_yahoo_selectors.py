import requests
from bs4 import BeautifulSoup

url_stats = 'https://soccer.yahoo.co.jp/jleague/category/j1/game/2026102502/stats'
resp_stats = requests.get(url_stats, headers={'User-Agent': 'Mozilla/5.0'})
resp_stats.encoding = 'utf-8'
soup_stats = BeautifulSoup(resp_stats.text, 'html.parser')

print('=== STATS TABLES ===')
for i, table in enumerate(soup_stats.find_all('table')):
    parent_classes = table.parent.get('class', [])
    print(f"Table {i} parent class: {parent_classes}, table class: {table.get('class')}")
    rows = table.find_all('tr')
    print(f"  Rows count: {len(rows)}")
    if rows:
        headers = [c.get_text(strip=True) for c in rows[0].find_all(['th', 'td'])]
        print(f"  Row 0: {headers[:10]}")
    if len(rows) > 1:
        headers1 = [c.get_text(strip=True) for c in rows[1].find_all(['th', 'td'])]
        print(f"  Row 1: {headers1[:10]}")

url_text = 'https://soccer.yahoo.co.jp/jleague/category/j1/game/2026102502/text'
resp_text = requests.get(url_text, headers={'User-Agent': 'Mozilla/5.0'})
resp_text.encoding = 'utf-8'
soup_text = BeautifulSoup(resp_text.text, 'html.parser')

print('\n=== TEXT LIVE ITEMS ===')
items = soup_text.select('.sc-textLive__item')
print(f"Items count: {len(items)}")
if items:
    for item in items[:5]:
        time_el = item.select_one('.sc-textLive__status')
        team_el = item.select_one('.sc-textLive__name')
        text_el = item.select_one('.sc-textLive__text')
        print({
            'time': time_el.get_text(strip=True) if time_el else None,
            'team': team_el.get_text(strip=True) if team_el else None,
            'text': text_el.get_text(strip=True) if text_el else None,
        })
