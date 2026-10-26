import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # ネットワークリクエストのログ
        page.on('response', lambda resp: print(f"API/Response: {resp.url}") if 'api' in resp.url or 'json' in resp.url or 'spaia' in resp.url and 'js' not in resp.url and 'css' not in resp.url else None)
        
        print("Navigating to results...")
        await page.goto("https://spaia.jp/football/jleague/j1/results", wait_until="networkidle")
        
        # リンクの探索
        links = await page.eval_on_selector_all("a", "elements => elements.map(el => ({href: el.href, text: el.innerText.trim()}))")
        match_links = [l for l in links if any(k in l['href'] for k in ['game', 'match', 'result', 'detail', 'live']) and '/football/' in l['href']]
        print(f"Rendered match links: {len(match_links)}")
        for l in match_links[:15]:
            print(l['href'], l['text'][:30])
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
