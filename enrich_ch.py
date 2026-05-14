#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio, json
from collections import Counter
from pathlib import Path

from add_seller import classify, _clean_shop_title

data = json.loads(Path("products.json").read_text("utf-8"))
targets = [p for p in data["products"] if p.get("seller") == "tophotfashion" and p.get("type") in ("Other", "ACCESSORIES")]
print(f"補完対象: {len(targets)} 件")

weidian = [p for p in targets if "weidian" in p.get("purchase", "")]
taobao  = [p for p in targets if "weidian" not in p.get("purchase", "")]
print(f"  Weidian: {len(weidian)}, Taobao: {len(taobao)}")

async def enrich_weidian_all(products):
    from playwright.async_api import async_playwright
    results = {}
    sem = asyncio.Semaphore(6)

    async def fetch_one(browser, p):
        async with sem:
            try:
                page = await browser.new_page()
                await page.goto(p["purchase"], wait_until="domcontentloaded", timeout=20000)
                title = await page.title()
                await page.close()
                results[id(p)] = _clean_shop_title(title) if title else ""
            except Exception as e:
                print(f"  [ERR] {p['purchase']}: {e}")
                results[id(p)] = ""

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        await asyncio.gather(*[fetch_one(browser, p) for p in products])
        await browser.close()

    return results

print("Weidian タイトル取得中 (Playwright)...")
results = asyncio.run(enrich_weidian_all(weidian))

fixed_wd = 0
for p in weidian:
    t = results.get(id(p), "")
    if t:
        new_type = classify(t)
        if new_type == "Other":
            new_type = "ACCESSORIES"
        p["type"] = new_type
        fixed_wd += 1
    else:
        p["type"] = "ACCESSORIES"

print(f"Weidian 補完: {fixed_wd}/{len(weidian)} 件")

for p in taobao:
    p["type"] = "ACCESSORIES"
print(f"Taobao デフォルト: {len(taobao)} 件 -> ACCESSORIES")

Path("products.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")

toph = [p for p in data["products"] if p.get("seller") == "tophotfashion"]
print("\n最終タイプ分布:")
for t, n in Counter(p.get("type", "") for p in toph).most_common():
    print(f"  {t}: {n}")
