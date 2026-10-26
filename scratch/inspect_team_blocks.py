import requests
from bs4 import BeautifulSoup

url = 'https://soccer.yahoo.co.jp/jleague/category/j1/teams'
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

with open('scratch/team_blocks.txt', 'w', encoding='utf-8') as f:
    for a in soup.find_all('a', href=lambda x: x and '/teams/' in x and '/info' in x):
        parent = a.find_parent('li') or a.find_parent('div')
        f.write(str(parent) + '\n\n')
