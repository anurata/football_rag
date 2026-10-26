import sys
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://www.jleague.jp/match/j1/2024/022301/player/'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until='networkidle')
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, 'html.parser')

print("Page Title:", soup.title.get_text() if soup.title else "No title")

# 主なセクションや見出しを探す
for h in soup.find_all(['h2', 'h3', 'h4']):
    print(f"{h.name}: {h.get_text(strip=True)}")

# 選手名やスタッツを含む要素を探す
player_cards = soup.find_all(class_=lambda c: c and ('player' in c.lower() or 'stat' in c.lower()))
print(f"Player/Stat related classes found: {len(player_cards)}")
for c in player_cards[:10]:
    print(f"  class={c.get('class')}: {c.get_text(strip=True)[:60]}")
