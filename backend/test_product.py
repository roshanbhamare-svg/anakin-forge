import asyncio
from playwright.async_api import async_playwright

async def test_product():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page = await context.new_page()
        
        # A known laptop on amazon.in
        url = "https://www.amazon.in/HP-Smartchoice-i5-1235U-15-6-inch-15s-fq5330TU/dp/B0B6F5XJ5K/"
        print(f"Going to {url}")
        await page.goto(url)
        
        await page.wait_for_timeout(5000)
        
        html = await page.content()
        with open("product_html.txt", "w", encoding="utf-8") as f:
            f.write(html)
            
        print("HTML saved to product_html.txt")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_product())
