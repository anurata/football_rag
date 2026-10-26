import requests
from bs4 import BeautifulSoup

url_stats = 'https://soccer.yahoo.co.jp/jleague/category/j1/game/2026102502/stats'
resp_stats = requests.get(url_stats, headers={'User-Agent': 'Mozilla/5.0'})
resp_stats.encoding = 'utf-8'
soup = BeautifulSoup(resp_stats.text, 'html.parser')

sb = soup.select_one('.sc-scoreBoard')
if sb:
    print("ScoreBoard text:", sb.get_text(separator=' | ', strip=True))

title = soup.select_one('.sc-gameHeader__title, .sc-scoreBoard__header')
if title:
    print("Header title:", title.get_text(strip=True))

meta_items = soup.select('.sc-scoreBoard__infoItem, .sc-scoreBoard__info')
for m in meta_items:
    print("Meta:", m.get_text(strip=True))
