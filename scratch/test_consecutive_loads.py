import sys
import os
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath('.'))
from scrapers.jleague_official import resolve_canonical_match_id
from pipeline.normalizer import EntityNormalizer

sys.stdout.reconfigure(encoding='utf-8')
norm = EntityNormalizer()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()

    for idx in range(1, 8):
        url = f"https://www.jleague.jp/match/j1/2026/0808{idx:02d}/"
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1000)
            soup = BeautifulSoup(page.content(), "html.parser")
            mid, title = resolve_canonical_match_id(soup, url, norm)
            t_txt = soup.title.get_text(strip=True) if soup.title else ""
            h1 = soup.find('h1')
            h1_txt = h1.get_text(strip=True) if h1 else ""
            print(f"[{idx:02d}] {url} -> mid={mid}, title={title}")
            print(f"     Title: {t_txt[:60]}")
            print(f"     H1:    {h1_txt[:60]}")
        finally:
            page.close()

    browser.close()
