import asyncio, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = await ctx.new_page()
        print("ページ取得中...")
        await page.goto("https://www.spreadfinds.com/trusted-sellers", wait_until="networkidle", timeout=30000)
        print("title:", await page.title())
        content = await page.content()
        # yupoo リンクを探す
        import re
        yupoo_links = re.findall(r'https?://[^\s"\'<>]+yupoo[^\s"\'<>]*', content)
        print(f"\nYupoo リンク: {len(yupoo_links)} 件")
        for l in sorted(set(yupoo_links)):
            print(" ", l)
        # テキスト全体も保存
        text = await page.evaluate("() => document.body.innerText")
        with open("spreadfinds_content.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print("\nテキストを spreadfinds_content.txt に保存しました")
        await browser.close()

asyncio.run(main())
