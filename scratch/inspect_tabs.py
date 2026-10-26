from playwright.sync_api import sync_playwright
import time
from bs4 import BeautifulSoup

url = "https://www.jleague.jp/match/j1/2026/102505/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(2000)
    
    # ページタイトルや試合ヘッダー情報の取得テスト
    print("Page Title:", page.title())
    
    # タブ一覧の確認
    tab_links = page.query_selector_all("a[href*='#']")
    for t in tab_links:
        text = t.inner_text().strip()
        href = t.get_attribute("href")
        if any(keyword in text for keyword in ["サマリー", "ラインナップ", "戦評", "試合速報", "スタッツ"]):
            print(f"Tab found: {text} -> {href}")

    # 「戦評」タブをクリックしてみる
    review_link = page.query_selector("a[href*='#review']")
    if review_link:
        print("Clicking review tab...")
        review_link.click()
        page.wait_for_timeout(2000)
        with open("page_review.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("page_review.html saved.")

    browser.close()
