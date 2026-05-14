#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_scan.py  ―  PR15 セラー多様化バッチスキャン
=====================================================
新しいセラーのYupooをスキャンし、products.json に追加する。

使い方:
  python batch_scan.py             # 未処理の全セラーを順番に処理
  python batch_scan.py --list      # セラー一覧と進捗を表示
  python batch_scan.py --seller Tigerrep   # 特定セラーのみ再スキャン
  python batch_scan.py --dry-run   # スキャンせず進捗だけ確認
"""

import argparse, asyncio, io, json, re, sys, time
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs, unquote

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

PANDORA_DIR   = Path(__file__).parent
PRODUCTS_JSON = PANDORA_DIR / "products.json"
PROGRESS_FILE = PANDORA_DIR / "batch_progress.json"
DATA_DIR      = PANDORA_DIR / "data" / "sellers"   # 中間JSON保存先
MAX_ALBUMS    = 30    # セラーあたり最大アルバム数
REQ_SLEEP     = 0.6   # requestsリクエスト間隔

AFFCODE       = "a235412"
KAKOBUY_BASE  = "https://www.kakobuy.com/item/details"

REQ_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ja,en;q=0.9',
    'Referer': 'https://x.yupoo.com/',
}

PURCHASE_DOMAINS = [
    "taobao.com", "1688.com", "weidian.com",
    "tmall.com", "detail.tmall.com", "pinduoduo.com",
]

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ========== セラーリスト ==========
# 既にproducts.json登録済みセラーは除外:
#   pikachushop, elephant-factory, hotdog-official, kdi220(French Fish),
#   noghost(Dragonrep), angelking47, 2335499519(Koala)
NEW_SELLERS = [
    # (name, brand, yupoo_top, cat_url_or_None)
    # --- ストリートウェア ---
    ("Tigerrep",         "Supreme",       "https://tiger-official.x.yupoo.com/",        None),
    ("Firerep",          "Streetwear",    "https://firerep.x.yupoo.com/",               None),
    ("3Madman",          "Streetwear",    "https://3madman.x.yupoo.com/",               None),
    ("GOAT-official",    "Trapstar",      "https://goat-official.x.yupoo.com/",         None),
    ("SWAGGYMADE",       "Balenciaga",    "https://swaggymade.x.yupoo.com/",            None),
    ("Reobrothers",      "Nike Tech",     "http://repbros.x.yupoo.com/",                None),
    ("Survival-Cloth",   "Essentials",    "https://survival-cloth.x.yupoo.com/albums",  None),
    ("Jsonreps",         "Off-White",     "https://lanbo325.x.yupoo.com/",              None),
    ("Yishan-ess",       "Essentials",    "https://yishan-ess.x.yupoo.com/",            None),
    ("XiaoSan-Studio",   "Stone Island",  "https://vx798134596.x.yupoo.com/",           None),
    # --- スニーカー ---
    ("Pandavaultt",      "Sneakers",      "https://pandavault.x.yupoo.com/",            None),
    ("Repsun",           "Sneakers",      "https://repsunofficial.x.yupoo.com/",        None),
    ("QCXC",             "Sneakers",      "http://qcxcaj1.x.yupoo.com/",               None),
    ("ninemile",         "Sneakers",      "https://ninemile.x.yupoo.com/albums",        None),
    ("peter-Zhuang",     "Sneakers",      "https://5hkty.x.yupoo.com/",                None),
    ("Ice-Cream",        "Designer Shoes","http://1932084671.x.yupoo.com/",             None),
    ("TMF",              "Designer Shoes","https://tmf001.x.yupoo.com/albums",          None),
    ("Jade",             "Hermes Shoes",  "https://hongxing001.x.yupoo.com/categories/4798260",
                                          "https://hongxing001.x.yupoo.com/categories/4798260"),
    ("ace-Shop",         "Designer Shoes","https://ace-shop-100.x.yupoo.com/albums",    None),
    ("chengouhome",      "Designer Shoes","https://chengouhome.x.yupoo.com/",           None),
    # --- デザイナー ---
    ("Topacney",         "Acne Studio",   "https://topacney.x.yupoo.com/",              None),
    ("RepsKing",         "Moncler",       "https://repsking.x.yupoo.com/albums",        None),
    ("YRX",              "Moncler",       "https://yrxvip.x.yupoo.com/",               None),
    ("JIEYI168Y",        "Moncler",       "https://jieyi168x.x.yupoo.com/albums",       None),
    ("CPReps",           "CP Company",    "https://cprepscn.x.yupoo.com/",              None),
    ("Beverly-Luxery",   "Arc'teryx",     "https://beverly-luxury.x.yupoo.com/",        None),
    ("Dream-Remake",     "Arc'teryx",     "https://west42.x.yupoo.com/",               None),
    ("Sharkbreeder",     "Arc'teryx",     "https://shark-breeder.x.yupoo.com/",         None),
    ("Chaorenqi",        "Canada Goose",  "https://chaorenqihaodian.x.yupoo.com/",      None),
    ("King-of-Goose",    "Canada Goose",  "https://kog001.x.yupoo.com/albums",          None),
    ("Topami",           "Ami Paris",     "https://amiparis.x.yupoo.com/",              None),
    ("SAWG-SUPPLY",      "Balenciaga",    "https://swagsupply.x.yupoo.com/",            None),
    # --- バッグ・アクセサリー ---
    ("God-Mall",         "Bags",          "https://godmall.x.yupoo.com/",               None),
    ("Qingyunzi",        "Luxury Bags",   "https://qingyunzi.x.yupoo.com/",             None),
    ("topk8",            "Belts",         "https://topk8.x.yupoo.com/",                 None),
    ("Survival-Source",  "Jewelry",       "https://survivalsource.x.yupoo.com/albums",  None),
    ("Justinluxury",     "Accessories",   "https://justinluxury.x.yupoo.com/albums",    None),
    ("Misschen",         "Belts",         "https://misschen7.x.yupoo.com/",             None),
    # --- その他特化 ---
    ("CND-ISLAND",       "Socks",         "https://baymaxsocks.x.yupoo.com/",           None),
    ("Ezfashion",        "Jerseys",       "https://ezfashion.x.yupoo.com/",             None),
    ("OGwave",           "Hats",          "https://ogwave.x.yupoo.com/",                None),
    ("Nolan",            "Hats",          "https://nolan-8.x.yupoo.com/",              None),
    ("Lemonvip",         "Leather Jacket","https://lemonvip.x.yupoo.com/",              None),
    ("Newpd",            "Ralph Lauren",  "https://newdp.x.yupoo.com/",                 None),
    ("Repkingdom",       "Ralph Lauren",  "https://repkingdom.x.yupoo.com/",            None),
]

# ========== 商品タイプ分類 ==========
PRODUCT_TYPES = [
    ("SNEAKERS",    ["sneaker","shoe","jordan","dunk","air force","yeezy","kobe","lebron",
                     "vomero","samba","campus","ultraboost","foam runner","スニーカー","球鞋",
                     "运动鞋","篮球鞋","跑鞋","aj","nike air","new balance"]),
    ("HOODIES",     ["hoodie","hoody","hooded","zip hoodie","连帽卫衣","连帽","パーカ"]),
    ("JACKETS",     ["jacket","coat","shell","puffer","wind","ジャケット","外套","夹克",
                     "棉服","羽绒","棒球","arc'teryx","moncler","canada goose","cp company"]),
    ("SWEATERS",    ["sweater","crewneck","crew neck","knit","sweatshirt","pullover",
                     "圆领","卫衣","针织","毛衣"]),
    ("T-SHIRTS",    ["tee","t-shirt","t shirt","tank top","short sleeve","tシャツ","短袖","t恤"]),
    ("TOPS",        ["top","vest","polo","rugby","トップス","背心"]),
    ("SHIRTS",      ["shirt","flannel","oxford","button","シャツ","衬衫"]),
    ("SHORTS",      ["short","ショーツ","短裤","sweatshort"]),
    ("PANTS",       ["pant","jogger","sweatpant","trouser","denim","jeans","卫裤","长裤",
                     "工装裤","运动裤"]),
    ("BAGS",        ["bag","tote","backpack","pack","pouch","バッグ","背包","挎包"]),
    ("ACCESSORIES", ["cap","hat","beanie","sock","glove","keychain","belt","scarf",
                     "帽","袜","手套","钥匙","围巾","jersey"]),
]

def classify(title: str) -> str:
    tl = title.lower()
    for ptype, kws in PRODUCT_TYPES:
        for kw in kws:
            if kw in tl:
                return ptype
    return "Other"

# ========== Kakobuyリンク ==========
def to_kakobuy(url: str) -> str:
    if not url:
        return ""
    return f"{KAKOBUY_BASE}?url={quote(url, safe='')}&affcode={AFFCODE}"

def extract_purchase_url(url: str) -> str:
    if "yupoo.com/external" in url:
        parsed = urlparse(url)
        raw = parse_qs(parsed.query).get("url", [""])[0]
        return unquote(unquote(raw)).replace("&amp;", "&")
    return url

# ========== 進捗管理 ==========
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text("utf-8"))
    return {}

def save_progress(progress: dict):
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), "utf-8")

# ========== アルバムリスト取得 (requests) ==========
def get_album_list_requests(base_url: str, max_albums: int = MAX_ALBUMS) -> list[dict]:
    """requestsでアルバム一覧を取得（高速だがJSレンダリング不可）"""
    albums = []
    try:
        r = requests.get(base_url, headers=REQ_HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"    [HTTP {r.status_code}] {base_url}")
            return albums
        soup = BeautifulSoup(r.text, "lxml")
        domain = re.match(r"(https?://[^/]+)", base_url)
        if not domain:
            return albums
        base_domain = domain.group(1)
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not re.search(r"/albums/\d+", href):
                continue
            m = re.search(r"/albums/(\d+)", href)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            full_url = href if href.startswith("http") else base_domain + href
            title = a.get("title", "") or a.get_text(strip=True) or ""
            albums.append({
                "album_id": m.group(1),
                "title": title,
                "yupoo_url": full_url,
                "purchase": "",
                "kakobuy": "",
                "image": "",
            })
            if len(albums) >= max_albums:
                break
    except Exception as e:
        print(f"    [ERR] get_album_list: {e}")
    return albums

# ========== アルバム詳細取得 (Playwright非同期) ==========
async def fetch_album_detail(browser, alb: dict, sem: asyncio.Semaphore, idx: int, total: int):
    """1アルバムの購入リンク・画像を非同期取得"""
    async with sem:
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()
        try:
            await page.goto(alb["yupoo_url"], wait_until="domcontentloaded", timeout=40000)
            await asyncio.sleep(1.5)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # 購入リンク
            taobao = None
            for a in soup.find_all("a", href=True):
                h = a["href"]
                if "yupoo.com/external" in h:
                    taobao = extract_purchase_url(h); break
                if any(d in h for d in PURCHASE_DOMAINS):
                    taobao = extract_purchase_url(h); break
            if not taobao:
                pat = re.compile(
                    r'https?://[^\s\'"<>]*(?:' +
                    '|'.join(d.replace(".", r"\.") for d in PURCHASE_DOMAINS) +
                    r')[^\s\'"<>]*'
                )
                found = pat.findall(soup.get_text())
                if found:
                    taobao = extract_purchase_url(found[0])
            if not taobao:
                hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                for h in hrefs:
                    if "yupoo.com/external" in h:
                        taobao = extract_purchase_url(h); break
                    if any(d in h for d in PURCHASE_DOMAINS):
                        taobao = extract_purchase_url(h); break

            alb["purchase"] = taobao or ""
            alb["kakobuy"]  = to_kakobuy(taobao) if taobao else ""

            # タイトル (H1から上書き)
            h1 = soup.find("h1")
            if h1 and not alb["title"]:
                alb["title"] = h1.get_text(strip=True)

            # 画像
            if not alb.get("image"):
                imgs = await page.eval_on_selector_all(
                    "img", "els => els.map(e => e.getAttribute('data-src') || e.src || '')"
                )
                for src in imgs:
                    if src and ("photo.yupoo" in src or "uvd.yupoo" in src):
                        alb["image"] = src; break

            status = "+" if taobao else "-"
            print(f"   [{idx:03d}/{total}] {status} {alb['title'][:40]}", end="\r")
        except Exception as e:
            alb["purchase"] = ""
            alb["kakobuy"]  = ""
            try:
                print(f"   [{idx:03d}/{total}] [err] {str(e)[:30]}", end="\r")
            except Exception:
                pass
        finally:
            try:
                await page.close()
            except Exception:
                pass
            try:
                await ctx.close()
            except Exception:
                pass

async def fetch_all_albums(albums: list, workers: int = 5):
    from playwright.async_api import async_playwright
    sem = asyncio.Semaphore(workers)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        tasks = [
            fetch_album_detail(browser, alb, sem, i+1, len(albums))
            for i, alb in enumerate(albums)
        ]
        await asyncio.gather(*tasks)
        await browser.close()

# ========== Playwrightでアルバムリスト取得 (フォールバック) ==========
def get_album_list_playwright(base_url: str, max_albums: int = MAX_ALBUMS) -> list[dict]:
    """requestsで0件だった場合のフォールバック"""
    from playwright.sync_api import sync_playwright
    albums = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = ctx.new_page()
            page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            html = page.content()
            page.close(); ctx.close(); browser.close()

        domain = re.match(r"(https?://[^/]+)", base_url)
        if not domain:
            return albums
        base_domain = domain.group(1)
        soup = BeautifulSoup(html, "html.parser")
        seen = set()
        for a in soup.find_all("a", href=re.compile(r"/albums/\d+")):
            href = a.get("href", "")
            m = re.search(r"/albums/(\d+)", href)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            full_url = href if href.startswith("http") else base_domain + href
            title = a.get("title", "") or a.get_text(strip=True) or ""
            albums.append({
                "album_id": m.group(1),
                "title": title,
                "yupoo_url": full_url,
                "purchase": "",
                "kakobuy": "",
                "image": "",
            })
            if len(albums) >= max_albums:
                break
    except Exception as e:
        print(f"    [ERR] playwright album list: {e}")
    return albums

# ========== products.json 操作 ==========
def load_site_products() -> list[dict]:
    if PRODUCTS_JSON.exists():
        return json.loads(PRODUCTS_JSON.read_text("utf-8")).get("products", [])
    return []

def save_site_products(products: list[dict]):
    out = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(products),
        "products": products,
    }
    PRODUCTS_JSON.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")

def merge_to_site(existing: list, new_items: list) -> tuple[list, int]:
    existing_yupoo = {p["yupoo"] for p in existing}
    added = 0
    for item in new_items:
        if item["yupoo"] not in existing_yupoo:
            existing.append(item)
            existing_yupoo.add(item["yupoo"])
            added += 1
    return existing, added

# ========== セラースキャン ==========
def scan_seller(name: str, brand: str, top_url: str, cat_url) -> list[dict]:
    target = cat_url if cat_url else top_url
    print(f"  [scan] album list: {target}")

    # まずrequestsで試みる
    albums = get_album_list_requests(target)
    print(f"  -> requests: {len(albums)} albums")

    # 0件ならPlaywrightにフォールバック
    if not albums:
        print(f"  -> Playwright fallback...")
        albums = get_album_list_playwright(target)
        print(f"  -> Playwright: {len(albums)} albums")

    if not albums:
        print(f"  [WARN] no albums found: {name}")
        return []

    print(f"  [fetch] purchase links + images ({len(albums)} albums, 5 workers)...")
    asyncio.run(fetch_all_albums(albums, workers=5))
    print()

    # products.jsonフォーマットに変換
    products = []
    for alb in albums:
        if not alb.get("kakobuy"):
            continue  # 購入リンクなしはスキップ
        ptype = classify(alb["title"])
        products.append({
            "seller":    name,
            "brand":     brand,
            "type":      ptype,
            "title":     alb["title"],
            "yupoo":     alb["yupoo_url"],
            "purchase":  alb["purchase"],
            "kakobuy":   alb["kakobuy"],
            "image":     alb.get("image", ""),
            "price_cny": None,
            "price_jpy": None,
        })

    # 中間JSONに保存（再スキャン不要にするため）
    save_path = DATA_DIR / f"{name}.json"
    save_path.write_text(
        json.dumps({"seller": name, "brand": brand, "products": products},
                   ensure_ascii=False, indent=2), "utf-8"
    )
    print(f"  [save] {save_path.name}: {len(products)} products")
    return products

# ========== メイン処理 ==========
def show_list(progress: dict):
    print(f"\n{'Name':<22} {'Brand':<20} {'Status':<10} {'Count'}")
    print("-" * 65)
    for name, brand, top, cat in NEW_SELLERS:
        state = progress.get(name, {})
        status = "[DONE]" if state.get("done") else "[TODO]"
        count  = state.get("count", "-")
        print(f"{name:<22} {brand:<20} {status:<10} {count}")
    print()
    done  = sum(1 for n,*_ in NEW_SELLERS if progress.get(n, {}).get("done"))
    total = len(NEW_SELLERS)
    print(f"Progress: {done}/{total} done")

def run_batch(target_seller: str = None):
    progress = load_progress()

    for name, brand, top_url, cat_url in NEW_SELLERS:
        if target_seller and name.lower() != target_seller.lower():
            continue
        if not target_seller and progress.get(name, {}).get("done"):
            print(f"[skip] {name} (already done)")
            continue

        print(f"\n{'='*60}")
        print(f"[{name}] {brand}")
        print(f"{'='*60}")

        try:
            new_products = scan_seller(name, brand, top_url, cat_url)

            # products.json にマージ
            existing = load_site_products()
            merged, added = merge_to_site(existing, new_products)
            save_site_products(merged)
            print(f"  [ok] +{added} added -> products.json (total {len(merged)})")

            progress[name] = {"done": True, "count": added, "total": len(new_products)}
            save_progress(progress)

        except Exception as e:
            err_msg = str(e).encode("ascii", errors="replace").decode("ascii")
            print(f"  [err] {err_msg}")
            progress[name] = {"done": False, "error": str(e)}
            save_progress(progress)
            continue

    print(f"\n\n{'='*60}")
    print("Batch scan complete!")
    done = sum(1 for n,*_ in NEW_SELLERS if progress.get(n, {}).get("done"))
    print(f"Done: {done}/{len(NEW_SELLERS)} sellers")

    existing = load_site_products()
    from collections import Counter
    brands = Counter(p.get("brand","?") for p in existing)
    nikes  = sum(c for b,c in brands.items() if "nike" in b.lower() or b == "NIKE")
    print(f"\nTotal products: {len(existing)}")
    print(f"NIKE ratio: {nikes}/{len(existing)} = {nikes/len(existing)*100:.1f}%")
    print("\nNext step: python build_static.py")

# ========== エントリポイント ==========
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PR15 batch seller scanner")
    parser.add_argument("--list",   action="store_true", help="セラー一覧と進捗を表示")
    parser.add_argument("--seller", help="特定セラーのみ処理 (例: --seller Tigerrep)")
    parser.add_argument("--dry-run",action="store_true", help="進捗確認のみ（スキャンしない）")
    args = parser.parse_args()

    progress = load_progress()

    if args.list or args.dry_run:
        show_list(progress)
    else:
        run_batch(target_seller=args.seller)
