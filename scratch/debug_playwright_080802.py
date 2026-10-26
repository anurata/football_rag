import sys
import os
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath('.'))
from scrapers.jleague_official import resolve_canonical_match_id
from pipeline.normalizer import EntityNormalizer

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/match/j1/2026/080802/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1000)
    soup = BeautifulSoup(page.content(), "html.parser")
    browser.close()

title_text = soup.title.get_text(strip=True) if soup.title else ""
h1 = soup.find("h1")
h1_text = h1.get_text(strip=True) if h1 else ""

print("Playwright Title:", title_text)
print("Playwright H1:", h1_text)

norm = EntityNormalizer()
mid, t = resolve_canonical_match_id(soup, url, norm)
print(f"Result: mid={mid}, title={t}")
