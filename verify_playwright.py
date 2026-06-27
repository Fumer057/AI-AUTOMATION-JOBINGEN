import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    print("Starting Playwright verification...")
    async with async_playwright() as p:
        print("Launching Chromium...")
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        html_content = """
        <html>
            <body style="background-color: #0A2463; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif;">
                <h1>Playwright is working!</h1>
            </body>
        </html>
        """
        print("Setting HTML content...")
        await page.set_content(html_content)
        
        print("Taking screenshot...")
        await page.screenshot(path="playwright_test.png")
        print("Screenshot saved to playwright_test.png")
        
        await browser.close()
        print("Verification complete! Browser works.")

if __name__ == "__main__":
    asyncio.run(main())
