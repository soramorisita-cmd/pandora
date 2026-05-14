import sys, io, re, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        for label, url in [
            ("Jadeship/Weidian", "https://www.jadeship.com/item/weidian/7721460328"),
            ("Jadeship/Taobao",  "https://www.jadeship.com/item/taobao/887785056459"),
        ]:
            print(f"\n=== {label} ===")
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # セレクター探索
            for sel in [
                "[class*='price']", "[class*='Price']",
                ".price", "span[class*='cny']", "[class*='CNY']",
                "[data-testid*='price']",
            ]:
                els = page.locator(sel)
                c = await els.count()
                if c > 0:
                    txt = await els.first.inner_text()
                    print(f"  [{sel}]: '{txt.strip()[:80]}'")

            # ページソース
            html = await page.content()
            for pat in [
                r'"price"\s*:\s*"?([\d]+\.?\d*)"?',
                r'¥\s*([\d]+\.?\d*)',
                r'CNY\s*([\d]+\.?\d*)',
                r'"priceRmb"\s*:\s*"?([\d]+\.?\d*)"?',
                r'rmb\s*:\s*([\d]+\.?\d*)',
            ]:
                m = re.findall(pat, html)
                if m:
                    print(f"  regex [{pat[:35]}]: {m[:5]}")

            print(f"  page size: {len(html)} chars")
            await ctx.close()

        await browser.close()

asyncio.run(main())
