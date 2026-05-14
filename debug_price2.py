import sys, io, re, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.async_api import async_playwright

ITEM_ID = "7488912496"
TAOBAO_ID = "887785056459"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # ── Weidian ──────────────────────────────────────────────
        print("=== Weidian ===")
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            locale="zh-CN",
        )
        page = await ctx.new_page()
        await page.goto(
            f"https://weidian.com/item.html?itemID={ITEM_ID}",
            wait_until="networkidle", timeout=30000
        )
        await asyncio.sleep(2)

        # 価格要素を探す
        for sel in [
            ".goods-price", ".price", "[class*='price']",
            ".item-price", ".sale-price", "span[class*='Price']",
        ]:
            els = page.locator(sel)
            count = await els.count()
            if count > 0:
                txt = await els.first.inner_text()
                print(f"  selector [{sel}]: '{txt.strip()[:60]}'")

        # ページソースから価格パターンを検索
        html = await page.content()
        for pat in [
            r'"price"\s*:\s*"?([\d]+\.?\d*)"?',
            r'"skuPrice"\s*:\s*"?([\d]+\.?\d*)"?',
            r'"minPrice"\s*:\s*"?([\d]+\.?\d*)"?',
            r'¥\s*([\d]+\.?\d*)',
            r'[\d]+\.?\d* ?元',
        ]:
            matches = re.findall(pat, html)
            if matches:
                print(f"  regex [{pat[:40]}]: {matches[:5]}")

        # window.* から JSON を探す
        for pat in [r'window\.__NUXT__\s*=\s*(.+?)(?=\n|</script>)',
                    r'window\.__INITIAL_STATE__\s*=\s*(.+?)(?=\n|</script>)']:
            m = re.search(pat, html, re.DOTALL)
            if m:
                snippet = m.group(1)[:300]
                print(f"  window var found ({len(m.group(1))} chars): {snippet[:200]}")

        print(f"  (page length: {len(html)} chars)")
        await ctx.close()

        # ── Taobao ───────────────────────────────────────────────
        print("\n=== Taobao ===")
        ctx2 = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="zh-CN",
        )
        page2 = await ctx2.new_page()
        await page2.goto(
            f"https://item.taobao.com/item.htm?id={TAOBAO_ID}",
            wait_until="networkidle", timeout=30000
        )
        await asyncio.sleep(3)

        for sel in [
            ".tb-rmb-num", "[class*='Price--priceText']",
            "[class*='priceText']", ".price", "[itemprop='price']",
        ]:
            els = page2.locator(sel)
            count = await els.count()
            if count > 0:
                txt = await els.first.inner_text()
                print(f"  selector [{sel}]: '{txt.strip()[:60]}'")

        html2 = await page2.content()
        for pat in [
            r'"defaultItemPrice"\s*:\s*"?([\d]+\.?\d*)"?',
            r'"price"\s*:\s*"?([\d]+\.?\d*)"?',
        ]:
            matches = re.findall(pat, html2)
            if matches:
                print(f"  regex [{pat[:40]}]: {matches[:5]}")

        print(f"  (page length: {len(html2)} chars)")
        await ctx2.close()

        await browser.close()

asyncio.run(main())
