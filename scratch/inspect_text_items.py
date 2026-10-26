import requests
from bs4 import BeautifulSoup

url_text = 'https://soccer.yahoo.co.jp/jleague/category/j1/game/2026102502/text'
resp_text = requests.get(url_text, headers={'User-Agent': 'Mozilla/5.0'})
resp_text.encoding = 'utf-8'
soup_text = BeautifulSoup(resp_text.text, 'html.parser')

items = soup_text.select('.sc-textLive__item')
print(f"Total items: {len(items)}")

with open('scratch/sample_parsed_text.txt', 'w', encoding='utf-8') as f:
    for idx, item in enumerate(items):
        time_el = item.select_one('.sc-textLive__status')
        team_el = item.select_one('.sc-textLive__name')
        text_el = item.select_one('.sc-textLive__text')
        # アイコンやバッジがあるか
        badge_el = item.select_one('.sc-textLive__icon, .sc-textLive__badge')
        
        t_str = time_el.get_text(strip=True) if time_el else ''
        tm_str = team_el.get_text(strip=True) if team_el else ''
        txt_str = text_el.get_text(strip=True) if text_el else ''
        bd_str = badge_el.get_text(strip=True) if badge_el else ''
        
        f.write(f"[{idx}] {t_str} | {tm_str} | {bd_str} | {txt_str}\n")

print("Written scratch/sample_parsed_text.txt")
