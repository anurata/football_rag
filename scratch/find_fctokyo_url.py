from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://www.fctokyo.co.jp/game/", wait_until="networkidle")
    print("Title:", page.title())
    soup = BeautifulSoup(page.content(), "html.parser")
    
    with open("scratch/fctokyo_game_links.txt", "w", encoding="utf-8") as out:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if any(k in href for k in ["game", "match", "review", "fanzone"]) or "水戸" in text:
                out.write(f"{text} -> {href}\n")
    browser.close()

print("saved fctokyo_game_links.txt")
