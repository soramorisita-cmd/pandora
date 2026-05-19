# -*- coding: utf-8 -*-
"""
新ブランドを非インタラクティブでスキャンしてproducts.jsonに追加するスクリプト
"""
import sys, json, time, asyncio, threading
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

# add_product.pyの関数を再利用
from add_product import (
    parse_yupoo_url, fetch_rates, scrape_subcategories, scrape_albums,
    fetch_all_albums_async, classify, extract_batch_from_title,
    load_brand_json, save_brand_json, load_site_products, save_site_products,
    merge_to_site, to_kakobuy, brand_to_filename, reclassify_other,
    DATA_DIR, PRODUCTS_JSON
)
from playwright.sync_api import sync_playwright

BRANDS_TO_SCAN = [
    # (url, brand_name, model_name_or_None)
    ("https://loganhere.x.yupoo.com/categories/4549989", "Represent", None),
    ("https://loganhere.x.yupoo.com/categories/4620284", "Aime Leon Dore", None),
    ("https://loganhere.x.yupoo.com/categories/4549861", "KITH", None),
    ("https://loganhere.x.yupoo.com/categories/4550702", "Palace", None),
    ("https://loganhere.x.yupoo.com/categories/4551561", "Stussy", None),
]


def scan_brand(url: str, brand: str, model: str | None, ctx, browser):
    info = parse_yupoo_url(url)
    seller = info["seller"]
    print(f"\n{'='*50}")
    print(f"🔍 スキャン: {brand} / seller: {seller}")

    print("📂 サブカテゴリ確認中...")
    subcats = scrape_subcategories(url, ctx, model=model)

    if subcats:
        print(f"✅ サブカテゴリ: {len(subcats)}件")
        albums = []
        for sc in subcats:
            print(f"  [{sc['name']}] スキャン中...")
            sc_albums = scrape_albums(sc["url"], ctx)
            for a in sc_albums:
                a["type"] = sc["type"] or classify(a["title"])
                a["batch"] = sc["name"]
            albums.extend(sc_albums)
            print(f"   → {len(sc_albums)}件")
    else:
        print("📂 アルバム一覧取得中...")
        albums = scrape_albums(url, ctx)
        for a in albums:
            a["type"] = classify(a["title"])

    if not albums:
        print(f"❌ {brand}: アルバムなし、スキップ")
        return 0

    for a in albums:
        a.setdefault("purchase", None)
        a.setdefault("kakobuy", None)
        a.setdefault("price_cny", None)
        a.setdefault("price_jpy", None)
        a.setdefault("image", None)
        if model:
            a["model"] = model
        if not a.get("batch") and not subcats:
            a["batch"] = extract_batch_from_title(a.get("title", ""))

    from collections import Counter
    types_count = Counter(a["type"] for a in albums)
    print(f"📊 分類結果 ({len(albums)}件): " + ", ".join(f"{t}:{c}" for t,c in types_count.most_common()))

    print(f"🔗 購入リンク・画像取得中（並列5件）...")
    def run_async():
        asyncio.run(fetch_all_albums_async(albums, workers=5))
    t = threading.Thread(target=run_async)
    t.start()
    t.join()
    print()

    # Other再分類
    others = [a for a in albums if a["type"] == "Other" and a.get("purchase")]
    if others:
        print(f"🔄 Other再分類中... ({len(others)}件)")
        for i, alb in enumerate(others):
            new_type = reclassify_other(alb, ctx)
            if new_type != "Other":
                alb["type"] = new_type
        reclassified = sum(1 for a in others if a["type"] != "Other")
        print(f"   再分類: {reclassified}件")

    # ブランドJSONに保存
    data = load_brand_json(brand)
    data["brand"] = brand
    data["seller"] = seller
    existing_ids = {p.get("album_id") for p in data["products"]}
    for a in albums:
        if a["album_id"] not in existing_ids:
            data["products"].append(a)
            existing_ids.add(a["album_id"])
    save_brand_json(data)
    print(f"✅ {brand}: {len(data['products'])}件保存")
    return len(albums)


def main():
    fetch_rates()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        total = 0
        for url, brand, model in BRANDS_TO_SCAN:
            try:
                n = scan_brand(url, brand, model, ctx, browser)
                total += n
            except Exception as e:
                print(f"❌ {brand} エラー: {e}")

        ctx.close()
        browser.close()

    print(f"\n{'='*50}")
    print(f"📥 products.jsonにインポート中...")

    all_new = []
    for url, brand, model in BRANDS_TO_SCAN:
        path = DATA_DIR / brand_to_filename(brand)
        if not path.exists():
            continue
        data = json.loads(path.read_text("utf-8"))
        for p in data["products"]:
            all_new.append({
                "seller":    data.get("seller", ""),
                "brand":     brand,
                "type":      p.get("type", "Other"),
                "title":     p["title"],
                "yupoo":     p["yupoo_url"],
                "purchase":  p.get("purchase", ""),
                "kakobuy":   p.get("kakobuy", ""),
                "image":     p.get("image", ""),
                "price_cny": p.get("price_cny"),
                "price_jpy": p.get("price_jpy"),
            })

    existing = load_site_products()
    merged, added = merge_to_site(existing, all_new)
    save_site_products(merged)
    print(f"✅ {added}件追加（合計 {len(merged)}件）")

    if added > 0:
        import subprocess
        from pathlib import Path
        repo = Path(__file__).parent
        brands_str = ", ".join(b for _, b, _ in BRANDS_TO_SCAN)
        print("\n🏗  build_static.py 実行中...")
        r = subprocess.run([sys.executable, "build_static.py"], cwd=repo, capture_output=True, text=True)
        print(r.stdout[-2000:] if r.stdout else "")
        if r.returncode != 0:
            print("Build error:", r.stderr[-500:])

        print("\n📤 Git push中...")
        for cmd in [
            ["git", "add", "products.json", "data/", "category/", "brand/", "index.html", "sitemap.xml"],
            ["git", "add", "products/"],
            ["git", "commit", "-m", f"add: {brands_str} from loganhere yupoo"],
            ["git", "push"]
        ]:
            r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
            ok = r.returncode == 0 or "nothing to commit" in r.stdout
            print(f"  {'✓' if ok else '⚠'} {' '.join(cmd[:3])}")
            if not ok:
                print("   ", r.stderr[:200])

    print("\n🎉 完了！")


if __name__ == "__main__":
    main()
