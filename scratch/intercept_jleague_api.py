import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

url = "https://www.jleague.jp/match/j1/2024/022301/live/"

api_requests = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    def on_request(request):
        if "api" in request.url or "json" in request.url or "data" in request.url:
            api_requests.append(request.url)

    page.on("request", on_request)
    try:
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
    except Exception as e:
        print("Page load warning:", e)

    browser.close()

print(f"API / JSON Requests intercepted: {len(api_requests)}")
for r in api_requests:
    print(r)
