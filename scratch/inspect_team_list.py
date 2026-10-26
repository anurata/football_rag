import requests
from bs4 import BeautifulSoup

url = 'https://soccer.yahoo.co.jp/jleague/category/j1/teams'
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

with open('scratch/team_list.txt', 'w', encoding='utf-8') as f:
    for item in soup.find_all('li', class_=lambda c: c and 'sc-teamList__item' in c):
        f.write(item.get_text(separator=' | ', strip=True) + '\n')
        for a in item.find_all('a', href=True):
            f.write(f"  {a['href']}\n")
