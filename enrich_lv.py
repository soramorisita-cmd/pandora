#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Louis Vuitton の Other 商品を Kakobuy タイトルから分類する。"""
import asyncio, json
from collections import Counter
from pathlib import Path

from add_seller import classify, _clean_shop_title

data = json.loads(Path("products.json").read_text("utf-8"))
targets = [
    p for p in data["products"]
    if p.get("brand") == "Louis Vuitton"
    and p.get("type") == "Other"
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
                results[id(p)] = _clean_shop_title(titles[0]) if titles else ""
            except Exception:
                results[id(p)] = ""
            finally:
                if ctx:
                    await ctx.close()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        await asyncio.gather(*[fetch_one(browser, p) for p in products])
        await browser.close()

    return results

print("Kakobuy タイトル取得中...")
results = asyncio.run(enrich_all(targets))

fixed = 0
for p in targets:
    t = results.get(id(p), "")
    if t:
        new_type = classify(t)
        if new_type != "Other":
            p["type"] = new_type
            fixed += 1
        # Other のまま → type は Other のままにする

print(f"補完: {fixed}/{len(targets)} 件")

Path("products.json").write_text(
    json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8"
)

lv = [p for p in data["products"] if p.get("brand") == "Louis Vuitton"]
print("\nLV タイプ分布:")
for t, n in Counter(p.get("type", "") for p in lv).most_common():
    print(f"  {t}: {n}")
