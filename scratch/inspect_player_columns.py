import requests
from bs4 import BeautifulSoup

url_stats = 'https://soccer.yahoo.co.jp/jleague/category/j1/game/2026102502/stats'
resp_stats = requests.get(url_stats, headers={'User-Agent': 'Mozilla/5.0'})
resp_stats.encoding = 'utf-8'
soup = BeautifulSoup(resp_stats.text, 'html.parser')

table = soup.select_one('table.sc-tablePlayerStats')
rows = table.find_all('tr')

with open('scratch/player_columns.txt', 'w', encoding='utf-8') as f:
    f.write("Row 0 cells:\n")
    for th in rows[0].find_all(['th', 'td']):
        f.write(f"  {th.get_text(strip=True)} (colspan={th.get('colspan', 1)}, rowspan={th.get('rowspan', 1)})\n")

    f.write("\nRow 1 cells:\n")
    for th in rows[1].find_all(['th', 'td']):
        f.write(f"  {th.get_text(strip=True)} (colspan={th.get('colspan', 1)}, rowspan={th.get('rowspan', 1)})\n")

    f.write("\nSample player row (Row 2):\n")
    cells = [td.get_text(strip=True) for td in rows[2].find_all(['th', 'td'])]
    f.write(f"Total cells: {len(cells)}\n")
    for idx, val in enumerate(cells):
        f.write(f"  Col {idx}: {val}\n")

print("Written scratch/player_columns.txt")
