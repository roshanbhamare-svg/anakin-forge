import asyncio
from playwright.async_api import async_playwright

async def test_amazon():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://www.amazon.in/")
        search_box = page.locator("#twotabsearchtextbox")
        await search_box.fill("laptop 16gb ram")
        await search_box.press("Enter")
        
        await page.wait_for_selector("[data-component-type='s-search-result']", timeout=15000)
        
        results = await page.locator("[data-component-type='s-search-result']").all()
        if results:
            print("First result HTML snippet:")
            html = await results[0].inner_html()
            print(html[:2000]) # Print first 2000 chars
        else:
            print("No results found at all.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_amazon())
