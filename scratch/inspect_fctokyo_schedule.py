import requests
from bs4 import BeautifulSoup

url = 'https://soccer.yahoo.co.jp/jleague/category/j1/teams/270/schedule?gk=2'
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

with open('scratch/fctokyo_yahoo_schedule.txt', 'w', encoding='utf-8') as f:
    for tr in soup.find_all('tr'):
        text = tr.get_text(separator=' | ', strip=True)
        links = [a['href'] for a in tr.find_all('a', href=True) if '/game/' in a['href']]
        if links:
            f.write(f"{text} ===> {links}\n")
print('Done writing scratch/fctokyo_yahoo_schedule.txt')
