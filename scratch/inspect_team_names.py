import requests
from bs4 import BeautifulSoup

url = 'https://soccer.yahoo.co.jp/jleague/category/j1/teams'
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

# sc-teamList or チーム一覧ブロックを探す
for a in soup.find_all('a', href=True):
    if '/teams/' in a['href'] and ('/info' in a['href'] or '/schedule' in a['href']):
        team_id = a['href'].split('/teams/')[1].split('/')[0]
        name = a.get_text(strip=True)
        # 親要素からチーム名を探す
        parent_h = a.find_parent(['li', 'div', 'section']).find(['h1', 'h2', 'h3', 'h4', 'p', 'span'])
        pname = parent_h.get_text(strip=True) if parent_h else ''
        print(f"team_id={team_id}: {pname} (link_text={name})")
