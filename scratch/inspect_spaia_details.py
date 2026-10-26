import requests
from bs4 import BeautifulSoup

url = 'https://spaia.jp/football/jleague/j1/game/2025050301/text'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
resp = requests.get(url, headers=headers)
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')

with open('scratch/spaia_text_sample.txt', 'w', encoding='utf-8') as f:
    f.write(f"Title: {soup.title.string}\n\n")
    f.write("=== LINKS ===\n")
    for a in soup.find_all('a', href=True):
        if '/game/' in a['href']:
            f.write(f"{a['href']} | {a.get_text(strip=True)}\n")
            
    f.write("\n=== TEXT ITEMS ===\n")
    # テキスト速報の要素候補を探す
    for el in soup.find_all(['li', 'div', 'p', 'tr']):
        classes = el.get('class', [])
        cls_str = ' '.join(classes)
        if any(k in cls_str.lower() for k in ['live', 'text', 'timeline', 'comment', 'event']):
            f.write(f"[{cls_str}] {el.get_text(separator=' ', strip=True)[:120]}\n")

print("Written scratch/spaia_text_sample.txt")
