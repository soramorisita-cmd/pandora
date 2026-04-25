# -*- coding: utf-8 -*-
"""
scrape_to_json.py
─────────────────
Yupooセラーリストをスクレイプし products.json を生成する。
Cloudflare Pages のリポジトリフォルダに直接出力してから git push するだけで
カタログが更新される。

使い方:
  python scrape_to_json.py
  python scrape_to_json.py --sellers "elephant-factory,steven-1989"  # 特定セラーのみ
  python scrape_to_json.py --no-images   # 画像取得スキップ（高速テスト用）

出力:
  products.json  ← リポジトリの同じフォルダに置いてpushする
"""

import asyncio, argparse, hashlib, json, re, time
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import openpyxl

# ─────────────────── 設定 ───────────────────
SELLER_LIST_PATH = r"C:\Users\soram\Desktop\pandora\優秀セラーリスト_by_Pandora_Reps(1).xlsx"
OUTPUT_JSON      = r"C:\Users\soram\Desktop\pandora\products.json"   # ← リポジトリフォルダに合わせて変更
AFFCODE          = "a235412"
CACHE_DIR        = Path(r"C:\Users\soram\Desktop\yupoo_cache")
PAGE_TIMEOUT     = 25_000
REQUEST_DELAY    = 1.2

PLACEHOLDER_IMG  = ""   # 空文字 → HTML側でプレースホルダー表示

# ─────────────────── 分類フォールバック ───────────────────
def classify_by_name(title: str) -> str:
    t = str(title).upper()
    if any(k in t for k in ["TEE","T-SHIRT","短袖T恤","LS TEE","SHORT SLEEVE TEE"]): return "T-Shirt"
    if any(k in t for k in ["SWEATSHORT","SOCCER SHORT","FLEECE SHORT","短裤","SHORTS"]): return "Shorts"
    if any(k in t for k in ["SWEATPANT","JOGGER","卫裤","长裤","TRACK PANT","BONDAGE PANT"]): return "Sweatpant"
    if any(k in t for k in ["TRACKSUIT","TARCKSUIT","套装","CHEST PACK"]): return "Tracksuit"
    if any(k in t for k in ["PUFFER","DOWN JACKET","羽绒服","TREK JACKET","TRACK TOP",
                              "冲锋衣","夹克","外套","ZIP HOOD","VOID-ZIP","JACKET","COAT"]): return "Jacket"
    if any(k in t for k in ["HOODIE","HOOD-","HOODY","HOODED","连帽卫衣"]): return "Hoodie"
    if any(k in t for k in ["CREWNECK","SWEATER","圆领卫衣","卫衣","毛衣","针织"]): return "Crewneck"
    if any(k in t for k in ["CAP","BEANIE","HAT","帽","TRUCKER","SNAPBACK"]): return "Headwear"
    if any(k in t for k in ["BAG","TOTE","背包","挎包"]): return "Bag"
    if any(k in t for k in ["SOCK","袜","GLOVES","手套","KEYCHAIN","钥匙"]): return "Accessories"
    if any(k in t for k in ["POLO"]): return "Polo"
    if any(k in t for k in ["SHORT","短裤"]): return "Shorts"
    if any(k in t for k in ["T恤","短袖"]): return "T-Shirt"
    return "Other"

def to_kakobuy(url: str) -> str:
    if not url or url == "未取得": return ""
    return f"https://www.kakobuy.com/item/details?url={quote(url, safe='')}&affcode={AFFCODE}"

# ─────────────────── キャッシュ ───────────────────
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _ckey(url): return hashlib.md5(url.encode()).hexdigest()
def load_html_cache(url):
    p = CACHE_DIR / (_ckey(url) + ".html")
    return p.read_text("utf-8") if p.exists() else None
def save_html_cache(url, html):
    (CACHE_DIR / (_ckey(url) + ".html")).write_text(html, "utf-8")

IMG_CACHE_FILE = CACHE_DIR / "img_cache.json"
def load_img_cache():
    return json.loads(IMG_CACHE_FILE.read_text("utf-8")) if IMG_CACHE_FILE.exists() else {}
def save_img_cache(c):
    IMG_CACHE_FILE.write_text(json.dumps(c, ensure_ascii=False), "utf-8")

# ─────────────────── fetch ───────────────────
async def fetch(page, url):
    cached = load_html_cache(url)
    if cached: return cached
    for attempt in range(3):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            await asyncio.sleep(1.0 + attempt * 0.5)
            html = await page.content()
            save_html_cache(url, html)
            await asyncio.sleep(REQUEST_DELAY)
            return html
        except Exception as e:
            print(f"    [retry {attempt+1}] {e}")
            await asyncio.sleep(3 * (attempt + 1))
    return ""

# ─────────────────── 画像取得 ───────────────────
async def fetch_image(page, album_url, img_cache):
    key = _ckey(album_url)
    if key in img_cache: return img_cache[key]
    result = PLACEHOLDER_IMG
    try:
        html = await fetch(page, album_url)
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("src") or ""
            if "photo.yupoo" in src or "uvd.yupoo" in src:
                result = src
                break
    except Exception as e:
        print(f"    [img err] {e}")
    img_cache[key] = result
    save_img_cache(img_cache)
    return result

# ─────────────────── カテゴリ解析 ───────────────────
async def get_leaf_categories(page, seller):
    base = f"https://{seller}.x.yupoo.com"
    html = await fetch(page, f"{base}/categories")
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    seen, parents, children = set(), [], []
    for a in soup.find_all("a", href=re.compile(r"/categories/\d+")):
        href = a.get("href","")
        is_sub = "isSubCate=true" in href
        m = re.search(r"/categories/(\d+)", href)
        if not m: continue
        cid = m.group(1)
        name = a.get_text(strip=True)
        if not name or cid in seen: continue
        seen.add(cid)
        (children if is_sub else parents).append({"name": name, "cate_id": cid, "is_sub": is_sub})
    return children if children else parents

async def get_albums_in_cat(page, seller, cat):
    base = f"https://{seller}.x.yupoo.com"
    flag = "true" if cat.get("is_sub") else "false"
    await fetch(page, f"{base}/categories")
    html = await fetch(page, f"{base}/categories/{cat['cate_id']}?uid=1&isSubCate={flag}")
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    albums, seen = [], set()
    for a in soup.find_all("a", href=re.compile(r"/albums/\d+")):
        m = re.search(r"/albums/(\d+)", a.get("href",""))
        if not m: continue
        aid = m.group(1)
        if aid in seen: continue
        seen.add(aid)
        albums.append({
            "title": a.get_text(strip=True),
            "album_id": aid,
            "yupoo_url": f"{base}/albums/{aid}?uid=1&isSubCate={flag}&referrercate={cat['cate_id']}"
        })
    return albums

async def get_albums_flat(page, seller):
    base = f"https://{seller}.x.yupoo.com"
    await fetch(page, f"{base}/categories")
    html = await fetch(page, f"{base}/albums?uid=1")
    if not html: return []
    soup = BeautifulSoup(html, "html.parser")
    albums, seen = [], set()
    for a in soup.find_all("a", href=re.compile(r"/albums/\d+")):
        m = re.search(r"/albums/(\d+)", a.get("href",""))
        if not m: continue
        aid = m.group(1)
        if aid in seen: continue
        seen.add(aid)
        title = a.get_text(strip=True)
        albums.append({
            "title": title, "album_id": aid,
            "yupoo_url": f"{base}/albums/{aid}?uid=1&isSubCate=false&referrercate=",
            "category": classify_by_name(title)
        })
    return albums

# ─────────────────── Taobao URL ───────────────────
TAOBAO_RE = re.compile(r"item\.taobao\.com/item\.htm\?id=(\d+)")
WEIDIAN_RE = re.compile(r"shop\d+\.v\.weidian\.com/item\.html\?itemID=(\d+)")

async def get_purchase_url(page, album_url):
    html = await fetch(page, album_url)
    m = TAOBAO_RE.search(html)
    if m: return f"https://item.taobao.com/item.htm?id={m.group(1)}"
    m = WEIDIAN_RE.search(html)
    if m:
        shop = re.search(r"(shop\d+\.v\.weidian\.com)", html)
        if shop: return f"https://{shop.group(1)}/item.html?itemID={m.group(1)}"
    return ""

# ─────────────────── セラーリスト ───────────────────
def load_sellers(target=None):
    wb = openpyxl.load_workbook(SELLER_LIST_PATH, read_only=True, data_only=True)
    # セラー名は「シート1」のC列（index 2）
    ws = wb["シート1"]
    sellers = []
    for row in ws.iter_rows(min_row=4, values_only=True):
        val = row[2]  # C列
        if not val: continue
        s = str(val).strip().replace("\n", "").replace("\u3000", "").strip()
        if not s or s in ("セラー名", "Yupoo", "人気カテゴリ"): continue
        # URLの場合はドメインを抽出
        m = re.search(r"https?://([^.]+)\.x\.yupoo\.com", s)
        if m:
            sellers.append(m.group(1))
        else:
            # セラー名をそのまま使用（小文字・スペース除去）
            name = re.sub(r"[\s\u3000]+", "", s).lower()
            if name:
                sellers.append(name)
    wb.close()
    # 重複除去
    sellers = list(dict.fromkeys(sellers))
    if target:
        specified = [t.strip() for t in target.split(",")]
        sellers = [s for s in sellers if s in specified]
    return sellers

# ─────────────────── セラー処理 ───────────────────
async def scrape_seller(page, seller, fetch_images, img_cache):
    print(f"\n[{seller}]")
    products = []
    leaf_cats = await get_leaf_categories(page, seller)

    if leaf_cats:
        print(f"  カテゴリ {len(leaf_cats)}件")
        for cat in leaf_cats:
            albums = await get_albums_in_cat(page, seller, cat)
            print(f"  [{cat['name']}] {len(albums)}件")
            for album in albums:
                purchase = await get_purchase_url(page, album["yupoo_url"])
                img = await fetch_image(page, album["yupoo_url"], img_cache) if fetch_images else ""
                products.append({
                    "seller":    seller,
                    "type":      cat["name"],
                    "title":     album["title"],
                    "yupoo":     album["yupoo_url"],
                    "purchase":  purchase,
                    "kakobuy":   to_kakobuy(purchase),
                    "image":     img,
                    "source":    "yupoo-category",
                })
    else:
        print(f"  フラット構成 → キーワード分類")
        albums = await get_albums_flat(page, seller)
        for album in albums:
            purchase = await get_purchase_url(page, album["yupoo_url"])
            img = await fetch_image(page, album["yupoo_url"], img_cache) if fetch_images else ""
            products.append({
                "seller":    seller,
                "type":      album.get("category","Other"),
                "title":     album["title"],
                "yupoo":     album["yupoo_url"],
                "purchase":  purchase,
                "kakobuy":   to_kakobuy(purchase),
                "image":     img,
                "source":    "keyword-fallback",
            })

    print(f"  → {len(products)}件")
    return products

# ─────────────────── メイン ───────────────────
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sellers",   help="カンマ区切りセラー名（省略時は全件）")
    parser.add_argument("--no-images", action="store_true", help="画像取得スキップ")
    args = parser.parse_args()

    sellers = load_sellers(args.sellers)
    print(f"対象セラー: {len(sellers)}件")

    img_cache = load_img_cache()
    all_products = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.set_extra_http_headers({"Accept-Language": "ja,en;q=0.9"})

        for i, seller in enumerate(sellers, 1):
            print(f"\n({i}/{len(sellers)})", end="")
            try:
                p = await scrape_seller(page, seller, not args.no_images, img_cache)
                all_products.extend(p)
            except Exception as e:
                print(f"  ❌ {e}")

        await browser.close()

    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count":   len(all_products),
        "products": all_products,
    }
    Path(OUTPUT_JSON).parent.mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_JSON).write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n✅ {len(all_products)}件 → {OUTPUT_JSON}")
    print("次のステップ: git add products.json && git commit -m 'update catalog' && git push")

if __name__ == "__main__":
    asyncio.run(main())