from bs4 import BeautifulSoup

with open('scratch/page_flab_1021.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

with open('scratch/flab_cbp_tables.txt', 'w', encoding='utf-8') as out:
    for i, t in enumerate(soup.find_all('table')):
        txt = t.get_text()
        if any(w in txt for w in ['CBP', 'チャンスビルディング', 'パス', 'クロス', 'ドリブル', '奪取', '守備']):
            out.write(f"\n=================== TABLE {i} ===================\n")
            for r in t.find_all('tr'):
                cols = [c.get_text(strip=True) for c in r.find_all(['th', 'td'])]
                out.write(" | ".join(cols) + "\n")

print("Done")
