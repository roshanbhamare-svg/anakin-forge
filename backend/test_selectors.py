import asyncio
from playwright.async_api import async_playwright

async def test_amazon_search():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page = await context.new_page()
        await page.goto("https://www.amazon.in/s?k=coding+laptop")
        
        try:
            await page.wait_for_selector("a.a-link-normal:has(h2)", timeout=10000)
            links = await page.locator("a.a-link-normal:has(h2)").all()
            print(f"Found {len(links)} links with a.a-link-normal:has(h2)")
            
            links2 = await page.locator("h2").all()
            print(f"Found {len(links2)} links with just h2")
            
            links3 = await page.locator(".s-result-item h2 a").all()
            print(f"Found {len(links3)} links with .s-result-item h2 a")
        except Exception as e:
            print("Failed:", e)
            print("Page title:", await page.title())
            html = await page.content()
            with open("test_amazon_html.txt", "w") as f:
                f.write(html)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_amazon_search())
