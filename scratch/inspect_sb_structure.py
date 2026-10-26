import requests
from bs4 import BeautifulSoup

url = 'https://soccer.yahoo.co.jp/jleague/category/j1/game/2026102502/stats'
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

sb = soup.select_one('.sc-scoreBoard')
with open('scratch/sb_tags.txt', 'w', encoding='utf-8') as f:
    for el in sb.find_all(True):
        cls = ' '.join(el.get('class', []))
        text = el.get_text(strip=True)
        if text and len(text) < 40:
            f.write(f"<{el.name} class='{cls}'>: {text}\n")

print("Written scratch/sb_tags.txt")
