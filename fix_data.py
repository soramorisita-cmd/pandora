#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_data.py
-----------
1. ブランド名の修正: カテゴリ名をブランドとして登録している商品を修正
2. 画像のダウンロード: Yupoo外部URLの画像をローカルに保存

使い方:
  python fix_data.py            # 両方実行
  python fix_data.py --brands   # ブランド修正のみ
  python fix_data.py --images   # 画像DLのみ
"""

import argparse, io, json, os, re, sys, time
from pathlib import Path
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
PRODUCTS_JSON = ROOT / "products.json"
IMAGES_DIR = ROOT / "images"
IMAGES_DIR.mkdir(exist_ok=True)

SLEEP = 0.3   # 画像DL間隔（秒）

# ── ブランド検出キーワード（優先度順） ──────────────────────────────────────
BRAND_RULES = [
    # Nike / Jordan
    ("Jordan",       ["air jordan", "aj1", "aj 1", "aj3", "aj 3", "aj4", "aj 4",
                       "aj11", "aj 11", "jordan 1", "jordan 3", "jordan 4"]),
    ("NIKE",         ["nike", "air force", "af1", "air max", "dunk", "sb dunk",
                       "vomero", "cortez", "kobe", "lebron", "zoom fly", "invincible",
                       "pegasus", "waffle", "infinity run", "react"]),
    # Adidas
    ("Adidas",       ["adidas", "yeezy", "samba", "campus", "gazelle", "nmd",
                       "ultraboost", "ultra boost", "superstar", "stan smith",
                       "forum", "350", "500", "700", "boost", "4d"]),
    # New Balance
    ("New Balance",  ["new balance", "nb 550", "nb 574", "nb 2002", "nb 9060",
                       "990v", "9060", "1906", "574", "550"]),
    # Other sneaker brands
    ("Salomon",      ["salomon", "xt-6", "speedcross", "xa pro"]),
    ("Asics",        ["asics", "gel-", "nimbus", "kayano", "gel kayano"]),
    ("Puma",         ["puma"]),
    ("Reebok",       ["reebok", "reebok classic", "club c 85"]),
    ("Converse",     ["converse", "chuck taylor", "all star ct"]),
    ("Vans",         ["vans", "old skool", "sk8-hi", "slip-on"]),
    ("ON Running",   ["on running", "cloud surfer", "cloudmonster"]),
    # Luxury / Designer
    ("Hermes",       ["hermes", "hermès", "birkin", "kelly", "constance"]),
    ("Louis Vuitton",["louis vuitton", "l.v.", "lv bag", "neverfull", "speedy",
                       "damier", "monogram canvas", "pochette"]),
    ("Chanel",       ["chanel", "classic flap", "boy chanel", "coco"]),
    ("Gucci",        ["gucci", "dionysus", "marmont", "ophidia"]),
    ("Dior",         ["dior", "saddle bag", "book tote"]),
    ("Prada",        ["prada", "re-edition", "cleo"]),
    ("Bottega Veneta",["bottega", "cassette", "jodie"]),
    ("Balenciaga",   ["balenciaga", "triple s", "track runner", "speed trainer",
                       "defender", "le cagole"]),
    ("Celine",       ["celine", "ava bag", "triomphe"]),
    ("Loewe",        ["loewe", "puzzle", "hammock"]),
    ("Fendi",        ["fendi", "baguette", "peekaboo"]),
    ("Versace",      ["versace", "virtus"]),
    # Streetwear / Fashion
    ("Supreme",      ["supreme"]),
    ("Off-White",    ["off-white", "off white", "virgil"]),
    ("Stone Island", ["stone island"]),
    ("CP Company",   ["cp company", "c.p. company", "cp shell"]),
    ("Arc'teryx",    ["arcteryx", "arc'teryx", "arc teryx", "beta lt", "zeta"]),
    ("Canada Goose", ["canada goose", "expedition parka", "chateau parka"]),
    ("Moncler",      ["moncler", "maya", "montcla", "genius"]),
    ("Acne Studio",  ["acne studio", "acne studios"]),
    ("Ami Paris",    ["ami paris", "ami de coeur"]),
    ("Ralph Lauren", ["ralph lauren", "polo ralph", "polo rl", "rl polo"]),
    ("Lacoste",      ["lacoste", "polo lacoste"]),
    ("Tommy Hilfiger",["tommy hilfiger", "tommy jeans"]),
    ("Stussy",       ["stussy"]),
    ("ESSENTIALS",   ["essentials", "fog essentials", "fear of god"]),
    ("Trapstar",     ["trapstar"]),
    ("Syna World",   ["syna world"]),
    ("HELLSTAR",     ["hellstar"]),
    ("Sp5der",       ["sp5der", "sp5 der"]),
    ("Broken Planet",["broken planet"]),
    ("REPRESENT",    ["represent"]),
    ("Corteiz",      ["corteiz", "crtz"]),
    ("Brain Dead",   ["brain dead"]),
    ("Aimé Leon Dore",["aimé leon", "aime leon", "ald "]),
    # Accessories
    ("Gucci",        ["gucci belt", "gg belt", "gg supreme belt"]),
    ("Louis Vuitton",["lv belt", "louis vuitton belt"]),
    ("Ferragamo",    ["ferragamo"]),
    ("Dior",         ["dior saddle", "christian dior"]),
]

# カテゴリ名として誤用されているブランド名リスト
CAT_AS_BRAND = {
    "Sneakers", "Designer Shoes", "Hermes Shoes", "Bags", "Luxury Bags",
    "Belts", "Jewelry", "Accessories", "Socks", "Jerseys", "Hats",
    "Leather Jacket", "Streetwear", "Nike Tech",
}

# セラー → デフォルトブランド（タイトルから判定できなかった場合）
SELLER_BRAND_DEFAULT = {
    "Pandavaultt":    "NIKE",
    "Repsun":         "NIKE",
    "QCXC":           "NIKE",
    "ninemile":       "NIKE",
    "peter-Zhuang":   "NIKE",
    "Ice-Cream":      "Designer Shoes",
    "TMF":            "Designer Shoes",
    "Jade":           "Hermes",
    "ace-Shop":       "Designer Shoes",
    "chengouhome":    "Designer Shoes",
    "God-Mall":       "Bags",
    "Qingyunzi":      "Bags",
    "topk8":          "Belts",
    "Misschen":       "Belts",
    "Survival-Source":"Jewelry",
    "Justinluxury":   "Accessories",
    "CND-ISLAND":     "CND ISLAND",
    "Ezfashion":      "Jerseys",
    "OGwave":         "Hats",
    "Nolan":          "Hats",
    "Lemonvip":       "Leather Jacket",
    "Newpd":          "Ralph Lauren",
    "Repkingdom":     "Ralph Lauren",
    "Firerep":        "Streetwear",
    "3Madman":        "Streetwear",
    "Reobrothers":    "NIKE",
}

def detect_brand(title: str) -> str | None:
    tl = title.lower()
    for brand, keywords in BRAND_RULES:
        for kw in keywords:
            if kw in tl:
                return brand
    return None

# ── ブランド修正 ─────────────────────────────────────────────────────────────
def fix_brands():
    data = json.loads(PRODUCTS_JSON.read_text("utf-8"))
    products = data["products"]

    fixed = 0
    for p in products:
        title = p.get("title", "")
        seller = p.get("seller", "")
        current = p.get("brand", "")

        # タイトルキーワードで判定（全商品対象）
        new_brand = detect_brand(title)

        # キーワード不一致の場合、カテゴリ名ブランドのみセラーデフォルトで補完
        if not new_brand and current in CAT_AS_BRAND:
            new_brand = SELLER_BRAND_DEFAULT.get(seller)

        if not new_brand or new_brand == current:
            continue
        p["brand"] = new_brand
        fixed += 1

    data["products"] = products
    PRODUCTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8"
    )
    print(f"[brands] {fixed} 件のブランドを修正しました")

# ── 画像ダウンロード ─────────────────────────────────────────────────────────
DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://x.yupoo.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

def url_to_filename(url: str, album_id: str) -> str:
    ext = ".jpg"
    m = re.search(r"\.(jpe?g|png|webp|avif)(\?|$)", url, re.IGNORECASE)
    if m:
        ext = "." + m.group(1).lower().replace("jpeg", "jpg")
    return f"yupoo_{album_id}{ext}"

def download_images():
    data = json.loads(PRODUCTS_JSON.read_text("utf-8"))
    products = data["products"]

    yupoo_products = [
        p for p in products
        if p.get("image") and ("photo.yupoo" in p["image"] or "uvd.yupoo" in p["image"])
    ]
    print(f"[images] Yupoo外部URL: {len(yupoo_products)} 件をダウンロード中...")

    ok = skip = fail = 0
    for i, p in enumerate(yupoo_products):
        url = p["image"]
        # アルバムIDをyupoo URLから抽出 (フォールバック: インデックス)
        yupoo_url = p.get("yupoo", "")
        album_id_m = re.search(r"/albums/(\d+)", yupoo_url)
        album_id = album_id_m.group(1) if album_id_m else str(i)

        fname = url_to_filename(url, album_id)
        dest = IMAGES_DIR / fname

        if dest.exists():
            p["image"] = f"images/{fname}"
            skip += 1
            continue

        try:
            time.sleep(SLEEP)
            r = requests.get(url, headers=DL_HEADERS, timeout=10)
            if r.status_code == 200 and len(r.content) > 1000:
                dest.write_bytes(r.content)
                p["image"] = f"images/{fname}"
                ok += 1
            else:
                fail += 1
                if r.status_code != 200:
                    print(f"  [HTTP {r.status_code}] {url[:60]}")
        except Exception as e:
            fail += 1
            print(f"  [ERR] {str(e)[:50]}")

        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(yupoo_products)} 完了 (ok:{ok} skip:{skip} fail:{fail})")

    data["products"] = products
    PRODUCTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8"
    )
    print(f"[images] 完了: ok={ok} skip={skip} fail={fail}")

# ── エントリポイント ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--brands", action="store_true")
    parser.add_argument("--images", action="store_true")
    args = parser.parse_args()

    if not args.brands and not args.images:
        args.brands = args.images = True

    if args.brands:
        fix_brands()
    if args.images:
        download_images()

    if args.brands or args.images:
        print("\n次のステップ: python build_static.py")
