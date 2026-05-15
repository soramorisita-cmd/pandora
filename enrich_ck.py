#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""charlesking77 の Other 商品を Kakobuy タイトルから brand/type 補完する。"""
import asyncio, json
from collections import Counter
from pathlib import Path

from add_seller import classify, detect_brand_from_text, _clean_shop_title

data = json.loads(Path("products.json").read_text("utf-8"))
targets = [
    p for p in data["products"]
    if p.get("seller") == "charlesking77"
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

BATCH = 100

async def run_batched(products):
    all_results = {}
    for i in range(0, len(products), BATCH):
        batch = products[i:i+BATCH]
        print(f"  バッチ {i//BATCH + 1}: {i+1}〜{i+len(batch)}")
        r = await enrich_all(batch)
        all_results.update(r)
    return all_results

print("Kakobuy タイトル取得中...")
results = asyncio.run(run_batched(targets))

brand_fixed = 0
type_fixed = 0
for p in targets:
    t = results.get(id(p), "")
    if not t:
        continue
    new_brand = detect_brand_from_text(t)
    new_type = classify(t)
    if new_brand and p.get("brand") in ("Other", "", None):
        p["brand"] = new_brand
        brand_fixed += 1
    if new_type != "Other":
        p["type"] = new_type
        type_fixed += 1

print(f"ブランド補完: {brand_fixed}/{len(targets)} 件")
print(f"タイプ補完: {type_fixed}/{len(targets)} 件")

Path("products.json").write_text(
    json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8"
)

ck = [p for p in data["products"] if p.get("seller") == "charlesking77"]
print("\ncharlesking77 ブランド分布:")
for b, n in Counter(p.get("brand", "") for p in ck).most_common(15):
    print(f"  {b}: {n}")
print("\ncharlesking77 タイプ分布:")
for t, n in Counter(p.get("type", "") for p in ck).most_common():
    print(f"  {t}: {n}")
