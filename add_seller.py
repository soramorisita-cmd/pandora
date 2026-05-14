#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_seller.py  ―  セラー個別追加ツール（カテゴリからブランド自動判定）
=======================================================================
使い方:
  # ブランドをカテゴリ名から自動判定
  python add_seller.py --name baymaxsocks --url "https://baymaxsocks.x.yupoo.com/categories/140683?isSubCate=true"

  # ブランドを固定指定
  python add_seller.py --name tigerrep --url "https://tiger-official.x.yupoo.com/" --brand Supreme

  # ドライラン（スキャンせずカテゴリ構造だけ確認）
  python add_seller.py --name baymaxsocks --url "https://baymaxsocks.x.yupoo.com/categories/140683?isSubCate=true" --dry-run
"""

import argparse, asyncio, concurrent.futures, io, json, re, sys, time
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs, unquote
import requests
from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PANDORA_DIR       = Path(__file__).parent
PRODUCTS_JSON     = PANDORA_DIR / "products.json"
SELLER_BRANDS_JSON = PANDORA_DIR / "seller_brands.json"
DATA_DIR          = PANDORA_DIR / "data" / "sellers"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AFFCODE       = "a235412"
KAKOBUY_BASE  = "https://www.kakobuy.com/item/details"
MAX_ALBUMS    = 500
REQ_SLEEP     = 0.5

REQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
    "Referer": "https://x.yupoo.com/",
}

PURCHASE_DOMAINS = [
    "taobao.com", "1688.com", "weidian.com",
    "tmall.com", "detail.tmall.com", "pinduoduo.com",
]

# ── ブランドスラング辞書（長いフレーズ優先でマッチ） ─────────────────────
BRAND_SLANG: dict[str, str] = {
    # Nike — "nk" uses short word-boundary match
    "n*k": "NIKE", "nke": "NIKE", "nike": "NIKE", "nk": "NIKE",
    # Adidas
    "adidas": "Adidas", "adid": "Adidas", "ad": "Adidas",
    # Jordan
    "air jordan": "Jordan", "jordan": "Jordan", "aj": "Jordan",
    # NBA
    "nba": "NBA",
    # Stance
    "stan*ce": "Stance", "stance": "Stance",
    # Calvin Klein — "ck" uses short word-boundary, "c*k" uses asterisk match
    "calvin klein": "Calvin Klein", "c*k": "Calvin Klein", "ck": "Calvin Klein",
    # Supreme
    "supreme": "Supreme", "sup ": "Supreme",
    # Palace
    "palace": "Palace", "pala": "Palace",
    # Off-White
    "off-white": "Off-White", "off white": "Off-White", "off whit*e": "Off-White",
    # Yeezy / Adidas
    "yeezy calabasas": "Adidas", "yeezy": "Adidas",
    # Chrome Hearts
    "chrome hearts": "Chrome Hearts", "chrome heart": "Chrome Hearts",
    # Bape
    "a bathing ape": "Bape", "bape": "Bape",
    # Mastermind Japan
    "mastermind japan": "Mastermind Japan", "mastermind": "Mastermind Japan", "mmj": "Mastermind Japan",
    # Gallery Dept
    "gallery dept": "Gallery Dept",
    # Lanvin
    "lanvin": "Lanvin",
    # Ami Paris
    "ami paris": "Ami Paris", "ami ": "Ami Paris",
    # Amiri
    "amiri": "Amiri",
    # Jacquemus
    "jacquemus": "Jacquemus",
    # Rhude
    "rhude": "Rhude",
    # Travis Scott
    "travis scott": "Travis Scott", "travis": "Travis Scott",
    # Golf Wang / Odd Future (Tyler the Creator)
    "golf wang": "Golf Wang", "golf ": "Golf Wang", "odd future": "Odd Future",
    # Vetements
    "vetements": "Vetements", "vetement": "Vetements",
    # Human Made
    "human made": "Human Made",
    # Casablanca
    "casablanca": "Casablanca",
    # Hidden NY
    "hidden ny": "Hidden NY",
    # Eric Emanuel
    "eric emanuel": "Eric Emanuel",
    # Syna World
    "synaworld": "Syna World", "syna world": "Syna World",
    # Trapstar
    "trapstar": "Trapstar", "trap star": "Trapstar",
    # HELLSTAR
    "hellstar": "HELLSTAR",
    # Corteiz
    "corteiz": "Corteiz", "crtz": "Corteiz",
    # Ralph Lauren
    "ralph lauren": "Ralph Lauren", "polo rl": "Ralph Lauren", "polo": "Ralph Lauren",
    # Balenciaga
    "balenciaga": "Balenciaga",
    # Gucci
    "gucci": "Gucci",
    # New Balance
    "new balance": "New Balance",
    # Salomon
    "salomon": "Salomon",
    # Denim Tears
    "denim tears": "Denim Tears",
    # Broken Planet
    "broken planet": "Broken Planet",
    # Sp5der
    "sp5der": "Sp5der",
    # Stone Island
    "stone island": "Stone Island",
    # CP Company
    "cp company": "CP Company", "c.p. company": "CP Company",
    # Stussy — "stus" catches "stus**sy" (** normalize to spaces → " stus  sy " → " stus " found)
    "stussy": "Stussy", "stüssy": "Stussy", "stus": "Stussy",
    # Palm Angels
    "palm angels": "Palm Angels",
    # Vlone
    "vlone": "Vlone",
    # Fear of God / ESSENTIALS
    "fear of god": "ESSENTIALS", "fog": "ESSENTIALS", "essentials": "ESSENTIALS",
    # Heron Preston
    "heron preston": "Heron Preston",
    # Champion
    "champion": "Champion",
    # Wtaps
    "wtaps": "Wtaps",
    # Vans
    "vans": "Vans",
    # A-Cold-Wall*
    "a-cold-wall": "A-Cold-Wall*", "acw": "A-Cold-Wall*",
    # Maison Margiela
    "maison margiela": "Maison Margiela", "maison magiela": "Maison Margiela",
    "masion magiela": "Maison Margiela", "mm6": "Maison Margiela",
    # HUF
    "huf": "HUF",
    # Ader Error
    "ader error": "Ader Error",
    # Drew House
    "drew house": "Drew House",
    # Ambush
    "ambush": "Ambush",
    # Undefeated
    "undefeated": "Undefeated",
    # OVO (Drake)
    "ovo": "OVO",
    # Anti Social Social Club
    "anti social social club": "ASSC", "assc": "ASSC",
    # Acne Studios
    "acne studio": "Acne Studios", "acne studios": "Acne Studios",
    # The North Face
    "the north face": "The North Face", "tnf": "The North Face",
    # Cactus Plant Flea Market
    "cactus plant flea market": "CPFM", "cpfm": "CPFM",
    # Lululemon
    "lululemon": "Lululemon",
    # UGG
    "ugg": "UGG",
    # Alo Yoga
    "alo yoga": "Alo Yoga", "a*lo": "Alo Yoga",
    # ON Running
    "on running": "ON Running",
    # Dsquared2
    "dsquared": "Dsquared2", "dsq2": "Dsquared2", "dsq": "Dsquared2",
    # Noah
    "noah": "Noah",
    # Gosha Rubchinskiy
    "gosha rubchinskiy": "Gosha Rubchinskiy", "gosha": "Gosha Rubchinskiy",
    # Celine
    "celine": "Celine",
    # Prada
    "prada": "Prada",
    # Dior
    "dior": "Dior",
    # Louis Vuitton
    "louis vuitton": "Louis Vuitton", "lv ": "Louis Vuitton",
    # Hermes
    "hermes": "Hermes", "hermès": "Hermes",
    # Moncler
    "moncler": "Moncler",
    # Canada Goose
    "canada goose": "Canada Goose",
    # Arc'teryx
    "arc'teryx": "Arc'teryx", "arcteryx": "Arc'teryx",
}

# ── 商品タイプ分類 ───────────────────────────────────────────────────────
PRODUCT_TYPES = [
    ("SNEAKERS",    ["sneaker", "shoe", "jordan", "dunk", "air force", "yeezy", "kobe",
                     "samba", "campus", "ultraboost", "foam runner", "スニーカー", "球鞋",
                     "运动鞋", "篮球鞋", "跑鞋", "aj", "nike air", "new balance"]),
    ("SOCKS",       ["sock", "socks", "ソックス", "袜子", "袜"]),
    ("HOODIES",     ["hoodie", "hoody", "hooded", "zip hoodie", "连帽卫衣", "连帽", "パーカ"]),
    ("JACKETS",     ["jacket", "coat", "shell", "puffer", "wind", "ジャケット", "外套", "夹克",
                     "棉服", "羽绒", "棒球"]),
    ("SWEATERS",    ["sweater", "crewneck", "crew neck", "knit", "sweatshirt", "pullover",
                     "圆领", "卫衣", "针织", "毛衣"]),
    ("T-SHIRTS",    ["tee", "t-shirt", "t shirt", "tank top", "short sleeve", "tシャツ", "短袖", "长袖", "t恤"]),
    ("SHORTS",      ["short", "ショーツ", "短裤", "sweatshort"]),
    ("PANTS",       ["pant", "jogger", "sweatpant", "trouser", "denim", "jeans", "卫裤", "长裤"]),
    ("TOPS",        [r"\btop\b", "vest", "polo", "rugby"]),
    ("SHIRTS",      ["shirt", "flannel", "oxford", "button", "シャツ", "衬衫"]),
    ("BAGS",        ["bag", "tote", "backpack", "pack", "pouch", "バッグ", "背包", "挎包"]),
    ("HATS",        ["cap", "hat", "beanie", "bucket", "snapback", "帽"]),
    ("ACCESSORIES", ["belt", "keychain", "scarf", "glove", "wallet", "jersey",
                     "手套", "围巾", "钥匙", "腰带"]),
]

def classify(title: str) -> str:
    tl = title.lower()
    for ptype, kws in PRODUCT_TYPES:
        for kw in kws:
            if "\\" in kw:
                if re.search(kw, tl):
                    return ptype
            elif kw in tl:
                return ptype
    return "Other"

def needs_taobao_enrichment(title: str) -> bool:
    """タイトルから商品タイプを判定できない場合にTaobao補完が必要か"""
    return classify(title) == "Other"

SIMPLE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

def _clean_shop_title(raw: str) -> str:
    """Taobao/Weidian のページタイトルからサフィックスを除去"""
    t = raw.strip()
    t = re.sub(r'\s*[-_—|·]\s*(淘宝|天猫|Tmall|Taobao|1688|微店|weidian).*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*(淘宝|天猫|微店)$', '', t).strip()
    return t

def fetch_weidian_title(url: str) -> str:
    """Weidian URL から requests で商品名を取得（SSR対応）"""
    try:
        r = requests.get(url, headers=SIMPLE_HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return ""
        m = re.search(r'<title[^>]*>([^<]{4,200})</title>', r.text)
        if m:
            return _clean_shop_title(m.group(1))
        m = re.search(r'"name"\s*:\s*"([^"]{4,200})"', r.text)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return ""

async def fetch_taobao_title_pw(browser, url: str, sem: asyncio.Semaphore) -> str:
    """Playwright で Taobao 商品タイトルを取得"""
    async with sem:
        ctx = await browser.new_context(user_agent=SIMPLE_HEADERS["User-Agent"])
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            title = await page.title()
            if title:
                return _clean_shop_title(title)
        except Exception:
            pass
        finally:
            try: await page.close()
            except Exception: pass
            try: await ctx.close()
            except Exception: pass
    return ""

async def _enrich_taobao_async(targets: list) -> int:
    from playwright.async_api import async_playwright
    sem = asyncio.Semaphore(5)
    enriched = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        tasks = [fetch_taobao_title_pw(browser, p["purchase"], sem) for p in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()
    for p, res in zip(targets, results):
        if isinstance(res, str) and len(res) > 4:
            p["taobao_title"] = res
            enriched += 1
    return enriched

def enrich_titles_from_taobao(products: list) -> int:
    """分類不能タイトルの商品について Taobao/Weidian から商品名を取得し taobao_title に保存"""
    targets = [p for p in products if p.get("purchase") and needs_taobao_enrichment(p.get("title", ""))]
    if not targets:
        return 0
    print(f"  [taobao] 分類不能 {len(targets)} 件のタイトルを補完中...")

    enriched = 0
    weidian = [p for p in targets if "weidian.com" in p.get("purchase", "")]
    taobao  = [p for p in targets if "weidian.com" not in p.get("purchase", "")]

    # Weidian は requests で並列取得
    if weidian:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(fetch_weidian_title, p["purchase"]): p for p in weidian}
            for fut in concurrent.futures.as_completed(futs):
                p = futs[fut]
                try:
                    t = fut.result()
                    if t:
                        p["taobao_title"] = t
                        enriched += 1
                except Exception:
                    pass

    # Taobao は Playwright で取得
    if taobao:
        enriched += asyncio.run(_enrich_taobao_async(taobao))

    print(f"  [taobao] {enriched}/{len(targets)} 件補完完了")
    return enriched

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

# ── ブランド判定 ─────────────────────────────────────────────────────────
def detect_brand_from_text(text: str) -> str | None:
    """テキストからブランドを判定（長いフレーズ優先、記号はスペースに正規化）"""
    # 記号（&、$、—、!等）をスペースに正規化。アスタリスクは残す
    normalized = re.sub(r'[^a-z0-9\s\*]', ' ', text.lower().strip())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    tl = " " + normalized + " "

    for slang, brand in sorted(BRAND_SLANG.items(), key=lambda x: -len(x[0])):
        if "*" in slang:
            # アスタリスク含むパターン（n*k, c*k, off whit*e 等）は正規化前テキストでも確認
            raw_tl = " " + text.lower().strip() + " "
            if slang in raw_tl or slang in tl:
                return brand
        elif slang.endswith(" "):
            # スペース末尾キー（"sup ", "ami " 等）
            if slang in tl:
                return brand
        elif len(slang) <= 4:
            # 短いキー（aj, nk, ck 等）はワードバウンダリ必須
            if f" {slang} " in tl:
                return brand
        else:
            # 長いフレーズはサブストリング一致
            if slang in normalized:
                return brand
    return None

def parse_category_brands(cat_name: str) -> list[str]:
    """カテゴリ名を '&' '$' で分割し、各部分のブランドリストを返す"""
    parts = re.split(r"[&$]", cat_name)
    brands: list[str] = []
    for part in parts:
        b = detect_brand_from_text(part.strip())
        if b and b not in brands:
            brands.append(b)
    return brands

def assign_brand(album_title: str, cat_brands: list[str], fixed_brand: str | None) -> str:
    """アルバムのブランドを決定。優先度: 固定指定 > アルバム名検出 > カテゴリブランド"""
    if fixed_brand:
        return fixed_brand
    b = detect_brand_from_text(album_title)
    if b:
        return b
    return cat_brands[0] if cat_brands else "Other"

# ── カテゴリ取得 ─────────────────────────────────────────────────────────
def get_base_domain(url: str) -> str:
    m = re.match(r"(https?://[^/]+)", url)
    return m.group(1) if m else ""

def fetch_categories_requests(url: str) -> list[dict]:
    """カテゴリ一覧を requests で取得 (name, url)"""
    cats = []
    try:
        r = requests.get(url, headers=REQ_HEADERS, timeout=15)
        if r.status_code != 200:
            return cats
        base = get_base_domain(url)
        # カテゴリリンクを抽出
        for m in re.finditer(r'<a[^>]+href="(/categories/\d+[^"]*)"[^>]*>([^<]{2,80})<', r.text):
            href, name = m.group(1), m.group(2).strip()
            name = re.sub(r"&amp;", "&", name)
            cat_url = base + href if not href.startswith("http") else href
            if name and not any(c["url"] == cat_url for c in cats):
                cats.append({"name": name, "url": cat_url})
    except Exception as e:
        print(f"  [ERR] fetch_categories: {e}")
    return cats

def fetch_categories_playwright(url: str) -> list[dict]:
    """requestsで0件のときのフォールバック"""
    from playwright.sync_api import sync_playwright
    cats = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context().new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            html = page.content()
            page.close(); browser.close()
        base = get_base_domain(url)
        for m in re.finditer(r'<a[^>]+href="(/categories/\d+[^"]*)"[^>]*>([^<]{2,80})<', html):
            href, name = m.group(1), m.group(2).strip()
            name = re.sub(r"&amp;", "&", name)
            cat_url = base + href if not href.startswith("http") else href
            if name and not any(c["url"] == cat_url for c in cats):
                cats.append({"name": name, "url": cat_url})
    except Exception as e:
        print(f"  [ERR] fetch_categories_playwright: {e}")
    return cats

def get_categories(url: str) -> list[dict]:
    cats = fetch_categories_requests(url)
    if not cats:
        print("  requests で0件 → Playwright にフォールバック")
        cats = fetch_categories_playwright(url)
    return cats

# ── アルバムリスト取得 ────────────────────────────────────────────────────
def get_albums_in_url(base_url: str, max_albums: int = MAX_ALBUMS) -> list[dict]:
    """URL（カテゴリページ or アルバムページ）からアルバムリストを取得（ページネーション対応）"""
    all_albums: list[dict] = []
    seen: set[str] = set()
    base_domain = get_base_domain(base_url)
    sep = "&" if "?" in base_url else "?"

    for page_num in range(1, 999):
        page_url = base_url if page_num == 1 else f"{base_url}{sep}page={page_num}"
        page_albums: list[dict] = []
        try:
            r = requests.get(page_url, headers=REQ_HEADERS, timeout=15)
            if r.status_code != 200:
                break
            for a in BeautifulSoup(r.text, "lxml").find_all("a", href=True):
                href = a["href"]
                m = re.search(r"/albums/(\d+)", href)
                if not m or m.group(1) in seen:
                    continue
                seen.add(m.group(1))
                full_url = href if href.startswith("http") else base_domain + href
                title = a.get("title", "") or a.get_text(strip=True) or ""
                page_albums.append({"album_id": m.group(1), "title": title,
                                    "yupoo_url": full_url, "purchase": "", "kakobuy": "", "image": ""})
        except Exception as e:
            print(f"  [ERR] get_albums page {page_num}: {e}")
            break

        if not page_albums:
            break
        all_albums.extend(page_albums)
        if len(all_albums) >= max_albums:
            break
        time.sleep(REQ_SLEEP)

    if not all_albums:
        # Playwright フォールバック（requestsで0件のとき）
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_context().new_page()
                page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                html = page.content()
                page.close(); browser.close()
            for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
                href = a.get("href", "")
                m = re.search(r"/albums/(\d+)", href)
                if not m or m.group(1) in seen:
                    continue
                seen.add(m.group(1))
                full_url = href if href.startswith("http") else base_domain + href
                title = a.get("title", "") or a.get_text(strip=True) or ""
                all_albums.append({"album_id": m.group(1), "title": title,
                                   "yupoo_url": full_url, "purchase": "", "kakobuy": "", "image": ""})
                if len(all_albums) >= max_albums:
                    break
        except Exception as e:
            print(f"  [ERR] playwright albums: {e}")
    return all_albums

# ── アルバム詳細取得 (Playwright 非同期) ─────────────────────────────────
async def fetch_album_detail(browser, alb: dict, sem: asyncio.Semaphore, idx: int, total: int):
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

            # タイトル
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
            print(f"   [{idx:03d}/{total}] {status} {alb.get('title','')[:40]}", end="\r")
        except Exception as e:
            alb["purchase"] = alb["kakobuy"] = ""
            print(f"   [{idx:03d}/{total}] [err] {str(e)[:30]}", end="\r")
        finally:
            for obj in (page, ctx):
                try: await obj.close()
                except Exception: pass

async def fetch_all_albums(albums: list, workers: int = 5):
    from playwright.async_api import async_playwright
    sem = asyncio.Semaphore(workers)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        await asyncio.gather(*[
            fetch_album_detail(browser, alb, sem, i+1, len(albums))
            for i, alb in enumerate(albums)
        ])
        await browser.close()

# ── メイン ───────────────────────────────────────────────────────────────
def run(seller_name: str, url: str, fixed_brand: str | None, forced_type: str | None, direct: bool, dry_run: bool):
    print(f"\n[add_seller] セラー: {seller_name}  URL: {url}")
    print(f"            ブランド: {fixed_brand or 'auto'}  タイプ: {forced_type or 'auto'}  直接取得: {direct}")

    # 1. カテゴリ一覧を取得（--direct の場合はスキップしてURLから直接アルバム取得）
    if direct:
        print("\n[1] --direct モード: URLから直接アルバム取得")
        categories = [{"name": fixed_brand or "default", "url": url}]
    else:
        print("\n[1] カテゴリ取得中...")
        categories = get_categories(url)
        if not categories:
            print("  カテゴリが見つかりません。URLを直接アルバムとして処理します。")
            categories = [{"name": "default", "url": url}]
        print(f"  {len(categories)} カテゴリ検出:")
        for cat in categories:
            brands = parse_category_brands(cat["name"])
            brand_str = " / ".join(brands) if brands else "(不明)"
            print(f"    [{brand_str:25s}] {cat['name'][:60]}")

    if dry_run:
        print("\n[dry-run] ここで終了。実際に取得するには --dry-run を外してください。")
        return

    # 2. 各カテゴリのアルバムを収集
    print("\n[2] アルバム収集中...")
    all_albums: list[dict] = []
    for cat in categories:
        cat_brands = parse_category_brands(cat["name"])
        albums = get_albums_in_url(cat["url"])
        time.sleep(REQ_SLEEP)
        for alb in albums:
            alb["_cat_brands"] = cat_brands
        all_albums.extend(albums)
        print(f"  {cat['name'][:50]}: {len(albums)} 件")

    # アルバムがない場合 URL直接から取得
    if not all_albums:
        print("  カテゴリ内にアルバムなし → URL直接からアルバム取得")
        all_albums = get_albums_in_url(url)
        for alb in all_albums:
            alb["_cat_brands"] = []

    print(f"\n  合計 {len(all_albums)} 件のアルバムを発見")

    if not all_albums:
        print("[ERROR] アルバムが見つかりませんでした。URLを確認してください。")
        return

    # 3. 各アルバムの詳細取得 (Playwright)
    print(f"\n[3] アルバム詳細取得中 (購入リンク・画像)...")
    asyncio.run(fetch_all_albums(all_albums))
    print()

    # 3.5 IDのみタイトルの場合 Taobao から商品名を補完
    enrich_titles_from_taobao(all_albums)

    # 4. products.json 用データに変換（既存スキーマに合わせる）
    products = []
    for alb in all_albums:
        if not alb.get("kakobuy"):
            continue  # 購入リンクなしはスキップ
        cat_brands = alb.pop("_cat_brands", [])
        brand = assign_brand(alb.get("title", ""), cat_brands, fixed_brand)
        # 分類用テキスト: Taobaoタイトルがあればそちらを優先
        classify_text = alb.get("taobao_title") or alb.get("title", "")
        products.append({
            "seller":    seller_name,
            "brand":     brand,
            "type":      forced_type or classify(classify_text),
            "title":     alb.get("title", ""),
            "yupoo":     alb["yupoo_url"],
            "purchase":  alb.get("purchase", ""),
            "kakobuy":   alb["kakobuy"],
            "image":     alb.get("image", ""),
            "price_cny": "",
            "price_jpy": "",
            "model":     "",
            "batch":     "",
        })

    ok   = len(products)
    skip = len(all_albums) - ok
    print(f"[4] 変換完了: {ok} 件 (購入リンクなし: {skip} 件スキップ)")

    if not products:
        print("[ERROR] 追加できる商品がありません。")
        return

    # 5. セラー中間ファイル保存
    out_file = DATA_DIR / f"{seller_name}.json"
    out_file.write_text(
        json.dumps({"seller": seller_name, "brand": fixed_brand or "auto",
                    "products": products}, ensure_ascii=False, indent=2),
        "utf-8"
    )
    print(f"[5] 中間ファイル保存: {out_file}")

    # 6. products.json にマージ（yupoo URLで重複チェック）
    data = json.loads(PRODUCTS_JSON.read_text("utf-8"))
    existing_yupoo = {p.get("yupoo", "") for p in data["products"]}
    new_products = [p for p in products if p["yupoo"] not in existing_yupoo]
    data["products"].extend(new_products)
    PRODUCTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8"
    )
    print(f"[6] products.json に {len(new_products)} 件追加 (重複スキップ: {ok - len(new_products)} 件)")

    # 7. seller_brands.json を更新
    if SELLER_BRANDS_JSON.exists():
        sb = json.loads(SELLER_BRANDS_JSON.read_text("utf-8"))
    else:
        sb = {}
    if seller_name not in sb:
        sb[seller_name] = fixed_brand or "auto"
        SELLER_BRANDS_JSON.write_text(
            json.dumps(sb, ensure_ascii=False, indent=2), "utf-8"
        )
        print(f"[7] seller_brands.json を更新")

    print(f"\n完了！  次のステップ: python build_static.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name",    required=True, help="セラー識別名 (例: baymaxsocks)")
    parser.add_argument("--url",     required=True, help="YupooのURL")
    parser.add_argument("--brand",   default=None,  help="ブランド固定指定 (省略でauto)")
    parser.add_argument("--type",    default=None,  help="商品タイプ固定 (例: ACCESSORIES, SOCKS, SNEAKERS)")
    parser.add_argument("--direct",  action="store_true", help="カテゴリを解析せず直接URLからアルバム取得")
    parser.add_argument("--dry-run", action="store_true", help="カテゴリ構造だけ確認して終了")
    args = parser.parse_args()
    run(args.name, args.url, args.brand, args.type, args.direct, args.dry_run)
