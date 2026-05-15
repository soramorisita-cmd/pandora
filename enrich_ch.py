#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tophotfashion の type="ACCESSORIES" 商品を Kakobuy タイトルから再分類する。
Kakobuy は Taobao/Weidian 両対応で CAPTCHA なし。locale=en-US で英語タイトルを取得。
"""
import asyncio, json
from collections import Counter
from pathlib import Path

from add_seller import classify, _clean_shop_title

data = json.loads(Path("products.json").read_text("utf-8"))
targets = [
    p for p in data["products"]
    if p.get("seller") == "tophotfashion"
    and p.get("type") in ("Other", "ACCESSORIES")
    and p.get("kakobuy")
]
print(f"補完対象: {len(targets)} 件")

async def enrich_all(products):
    from playwright.async_api import async_playwright
    results = {}
    sem = asyncio.Semaphore(3)

    async def fetch_one(browser, p):
        async with sem:
            ctx = None
            try:
                ctx = await browser.new_context(locale="en-US")
                page = await ctx.new_page()
                await page.goto(p["kakobuy"], wait_until="load", timeout=60000)
                loc = page.locator(".item-title")
                await loc.first.wait_for(timeout=30000)
                titles = await loc.all_text_contents()
                t = _clean_shop_title(titles[0]) if titles else ""
                results[id(p)] = t
            except Exception as e:
                results[id(p)] = ""
            finally:
                if ctx:
                    await ctx.close()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        await asyncio.gather(*[fetch_one(browser, p) for p in products])
        await browser.close()

    return results

print("Kakobuy タイトル取得中 (Playwright, locale=en-US)...")
results = asyncio.run(enrich_all(targets))

fixed = 0
for p in targets:
    t = results.get(id(p), "")
    if t:
        new_type = classify(t)
        if new_type == "Other":
            new_type = "ACCESSORIES"
        p["type"] = new_type
        fixed += 1
    else:
        p["type"] = "ACCESSORIES"

print(f"補完: {fixed}/{len(targets)} 件")

Path("products.json").write_text(
    json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8"
)

toph = [p for p in data["products"] if p.get("seller") == "tophotfashion"]
print("\n最終タイプ分布:")
for t, n in Counter(p.get("type", "") for p in toph).most_common():
    print(f"  {t}: {n}")
