# -*- coding: utf-8 -*-
"""
fetch_prices.py — products.json に price_cny / price_jpy を付与する

戦略（優先順）:
  1. タイトル中の【Nyuan】パターン → 即時（16% / 547件）
  2. Weidian ページ Playwright → 53% / ~1784件
  3. Jadeship ページ Playwright → 4% / 138件
  4. Taobao モバイル Playwright → 成功率低いが試みる

使い方:
  python fetch_prices.py              # 全件（未取得のみ）
  python fetch_prices.py --limit 30   # 先頭N件でテスト
  python fetch_prices.py --dry-run    # 保存なし
  python fetch_prices.py --sync       # data/*.json にも反映
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json, re, time, asyncio, argparse
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from playwright.async_api import async_playwright, Browser

PRODUCTS_JSON = Path(__file__).parent / "products.json"
DATA_DIR      = Path(__file__).parent / "data"
SAVE_EVERY    = 100
WORKERS       = 5
CNY_TO_JPY    = 21.5

# ── 為替 ─────────────────────────────────────────────────────────────
def fetch_rates() -> float:
    global CNY_TO_JPY
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/CNY", timeout=5)
        rate = r.json()["rates"].get("JPY", CNY_TO_JPY)
        CNY_TO_JPY = rate
        print(f"[rate] 1 CNY = {rate:.2f} JPY")
    except Exception:
        print(f"[rate] fallback {CNY_TO_JPY} JPY")
    return CNY_TO_JPY

# ── URL ヘルパー ─────────────────────────────────────────────────────
def platform(url: str) -> str:
    if not url:
        return "unknown"
    h = urlparse(url).netloc.lower()
    if "taobao.com" in h:  return "taobao"
    if "weidian.com" in h: return "weidian"
    if "jadeship.com" in h: return "jadeship"
    return "unknown"

def weidian_item_id(url: str) -> str | None:
    qs = parse_qs(urlparse(url).query)
    return (qs.get("itemID") or qs.get("id") or [None])[0]

def taobao_item_id(url: str) -> str | None:
    return parse_qs(urlparse(url).query).get("id", [None])[0]

# ── ① タイトルから価格を取得（最速）───────────────────────────────
# パターン1: 【110yuan】【¥110】 形式
TITLE_PRICE_RE = re.compile(
    r'[【\[]\s*(\d+(?:\.\d+)?)\s*(?:yuan|cny|rmb|元|￥|¥)\s*[】\]]',
    re.IGNORECASE,
)
# パターン2: ￥127 / ¥ 105 / ￥~139（チルダあり）形式
TITLE_PRICE_RE2 = re.compile(r'[￥¥][~\s]*(\d+(?:\.\d+)?)')
# パターン2b: 160￥ / 50¥（数字が先）形式
TITLE_PRICE_RE2b = re.compile(r'(?<!\d)(\d+(?:\.\d+)?)\s*[￥¥]')
# パターン3: P585 / P430 形式（価格を P+数字で表す）
TITLE_PRICE_RE3 = re.compile(r'\bP(\d{3,4})\b')
# パターン4: 【数字】 形式（【520】など、カッコ内が3桁以上の数字のみ）
TITLE_PRICE_RE4 = re.compile(r'[【\[](\d{3,5})[】\]]')
# パターン5: 【440Y】【 320Y 】 形式（Y=yuan、スペース許容）
TITLE_PRICE_RE5 = re.compile(r'[【\[]\s*(\d{2,4})\s*[Yy]\s*[】\]]')

def price_from_title(title: str) -> float | None:
    # パターン1: 【110yuan】
    m = TITLE_PRICE_RE.search(title)
    if m:
        v = float(m.group(1))
        if 10 < v < 10_000:
            return v
    # パターン2: ￥127 / ¥ 105
    m = TITLE_PRICE_RE2.search(title)
    if m:
        v = float(m.group(1))
        if 10 < v < 10_000:
            return v
    # パターン2b: 160￥ / 50¥（数字が先）
    m = TITLE_PRICE_RE2b.search(title)
    if m:
        v = float(m.group(1))
        if 10 < v < 10_000:
            return v
    # パターン3: P585（先頭に来るものを優先）
    m = TITLE_PRICE_RE3.match(title.strip())
    if m:
        v = float(m.group(1))
        if 10 < v < 10_000:
            return v
    # パターン4: 【520】
    m = TITLE_PRICE_RE4.search(title)
    if m:
        v = float(m.group(1))
        if 10 < v < 10_000:
            return v
    # パターン5: 【440Y】
    m = TITLE_PRICE_RE5.search(title)
    if m:
        v = float(m.group(1))
        if 10 < v < 10_000:
            return v
    return None

# ── ② ページ HTML から価格を抽出（共通）────────────────────────────
PRICE_RE = re.compile(r'[¥￥]\s*([\d]+(?:\.[\d]+)?)')  # 半角¥・全角￥両対応
KAKOBUY_CNY_RE = re.compile(r'CNY\s*[¥￥]\s*([\d]+(?:\.[\d]+)?)')  # Kakobuy CNY表示専用
JSON_PRICE_RE = re.compile(
    r'"(?:price|skuPrice|minPrice|currentPrice|priceRmb)"\s*:\s*"?([\d]+(?:\.[\d]+)?)"?'
)

def parse_price(text: str) -> float | None:
    # ¥表記（最も信頼性高い）
    for m in PRICE_RE.finditer(text):
        v = float(m.group(1))
        if 1 < v < 100_000:
            return v
    # JSONフィールド
    for m in JSON_PRICE_RE.finditer(text):
        v = float(m.group(1))
        if 1 < v < 100_000:
            return v
    return None

# ── Playwright 共通取得ロジック ──────────────────────────────────────
async def fetch_page_price(url: str, browser: Browser) -> float | None:
    ctx = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        locale="zh-CN",
    )
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=35_000)
        await asyncio.sleep(2)
        html = await page.content()
        return parse_price(html)
    except Exception:
        return None
    finally:
        await page.close()
        await ctx.close()

async def fetch_weidian(purchase_url: str, browser: Browser) -> float | None:
    item_id = weidian_item_id(purchase_url)
    if not item_id:
        return None
    target = f"https://weidian.com/item.html?itemID={item_id}"
    return await fetch_page_price(target, browser)

async def fetch_taobao(purchase_url: str, browser: Browser) -> float | None:
    item_id = taobao_item_id(purchase_url)
    if not item_id:
        return None
    # モバイル版を試みる
    target = f"https://h5.m.taobao.com/awp/core/detail.htm?id={item_id}"
    return await fetch_page_price(target, browser)

async def fetch_jadeship(purchase_url: str, browser: Browser) -> float | None:
    return await fetch_page_price(purchase_url, browser)

async def fetch_kakobuy(kakobuy_url: str, browser: Browser) -> float | None:
    """KakobuyページからCNY価格を取得（Taobaoの代替）"""
    if not kakobuy_url:
        return None
    ctx = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        locale="zh-CN",
    )
    page = await ctx.new_page()
    try:
        await page.goto(kakobuy_url, wait_until="networkidle", timeout=35_000)
        await asyncio.sleep(2)
        # Kakobuyの価格要素を取得（CNY表示）
        price_text = await page.evaluate("""() => {
            const selectors = [
                '.item-price', '.price-cny', '.goods-price',
                '[class*="price"]', '.detail-price', '.sku-price'
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) return el.textContent;
            }
            // フォールバック: ページ全体から¥数字を探す
            return document.body.innerText;
        }""")
        if price_text:
            # Kakobuyは "CNY ￥593.59" 形式を優先
            m = KAKOBUY_CNY_RE.search(price_text)
            if m:
                v = float(m.group(1))
                if 10 < v < 50_000:
                    return v
            return parse_price(price_text)
        return None
    except Exception:
        return None
    finally:
        await page.close()
        await ctx.close()

# ── メインループ ─────────────────────────────────────────────────────
async def run(products: list[dict], limit: int | None, dry_run: bool):
    rate = fetch_rates()

    # Pass1対象: price_cny が null の全商品（purchase の有無問わずタイトルから試みる）
    title_targets = [
        (i, p) for i, p in enumerate(products)
        if p.get("price_cny") is None
    ]
    # Pass2対象: purchase URL がある商品（Playwright）
    pw_targets_all = [
        (i, p) for i, p in enumerate(products)
        if p.get("price_cny") is None and p.get("purchase")
    ]
    if limit:
        title_targets = title_targets[:limit]
        pw_targets_all = pw_targets_all[:limit]

    total = len(title_targets)
    print(f"\n対象: {total} 件（全 {len(products)} 件中）\n")

    # ── Pass 1: タイトルから即時取得 ─────────────────────────────────
    title_hit = 0
    playwright_queue: list[tuple[int, dict]] = []
    priced_by_title = set()

    for i, p in title_targets:
        price = price_from_title(p.get("title", ""))
        if price:
            if not dry_run:
                products[i]["price_cny"] = round(price, 2)
                products[i]["price_jpy"] = round(price * rate)
            title_hit += 1
            priced_by_title.add(i)
        elif p.get("purchase"):
            playwright_queue.append((i, p))

    print(f"[pass1] title: {title_hit} 件取得")
    if title_hit > 0 and not dry_run:
        _save(products)

    # ── Pass 2: Playwright ─────────────────────────────────────────
    pw_total   = len(playwright_queue)
    pw_success = 0
    pw_fail    = 0
    sem        = asyncio.Semaphore(WORKERS)
    results    = {}  # i → price_cny

    async def worker(idx: int, i: int, p: dict):
        async with sem:
            pf = platform(p["purchase"])
            price = None
            try:
                if pf == "weidian":
                    price = await fetch_weidian(p["purchase"], browser)
                elif pf == "jadeship":
                    price = await fetch_jadeship(p["purchase"], browser)
                elif pf == "taobao" and p.get("kakobuy"):
                    price = await fetch_kakobuy(p["kakobuy"], browser)
            except Exception:
                pass
            results[i] = price
            status = f"{price:.2f} CNY" if price else "fail"
            print(
                f"[{idx:04d}/{pw_total}] {pf:<10} "
                f"{p.get('title','')[:45]:45} -> {status}"
            )
            await asyncio.sleep(0.5)

    if playwright_queue:
        print(f"[pass2] Playwright: {pw_total} 件（workers={WORKERS}）\n")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            tasks = [
                worker(idx, i, p)
                for idx, (i, p) in enumerate(playwright_queue, 1)
            ]
            await asyncio.gather(*tasks)
            await browser.close()

        # 結果を products に書き込み
        for i, price in results.items():
            if price:
                if not dry_run:
                    products[i]["price_cny"] = round(price, 2)
                    products[i]["price_jpy"] = round(price * rate)
                pw_success += 1
            else:
                pw_fail += 1

        # 中間保存（pw完了後）
        if not dry_run:
            _save(products)

    # ── 最終集計 ─────────────────────────────────────────────────────
    total_success = title_hit + pw_success
    print(f"\n=== 完了 ===")
    print(f"タイトル取得: {title_hit} 件")
    print(f"Playwright:  {pw_success} 件成功 / {pw_fail} 件失敗")
    print(f"合計取得:    {total_success} / {total} 件 ({100*total_success//max(total,1)}%)")
    if dry_run:
        print("(dry-run: 保存なし)")

def _save(products: list[dict]):
    data = json.load(open(PRODUCTS_JSON, encoding="utf-8"))
    data["products"] = products
    PRODUCTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("  [save] products.json 更新")

def sync_brand_jsons(products: list[dict]):
    price_map = {
        p["yupoo"]: (p.get("price_cny"), p.get("price_jpy"))
        for p in products if p.get("price_cny") is not None
    }
    for path in DATA_DIR.glob("*.json"):
        brand = json.loads(path.read_text("utf-8"))
        changed = False
        for item in brand.get("products", []):
            key = item.get("yupoo_url", "")
            if key in price_map:
                cny, jpy = price_map[key]
                if item.get("price_cny") != cny:
                    item["price_cny"] = cny
                    item["price_jpy"] = jpy
                    changed = True
        if changed:
            path.write_text(json.dumps(brand, ensure_ascii=False, indent=2), "utf-8")
            print(f"  [sync] {path.name}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",   type=int,         help="件数上限（テスト用）")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sync",    action="store_true", help="data/*.json にも反映")
    args = parser.parse_args()

    data     = json.load(open(PRODUCTS_JSON, encoding="utf-8"))
    products = data["products"]
    asyncio.run(run(products, args.limit, args.dry_run))

    if args.sync and not args.dry_run:
        print("\n[sync] data/ を更新中...")
        sync_brand_jsons(products)

if __name__ == "__main__":
    main()
