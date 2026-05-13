# -*- coding: utf-8 -*-
"""
build_static.py — PR1 SSG ビルドスクリプト

生成物:
  products/{album_id}.html   個別商品ページ（全件）
  category/{type}/index.html カテゴリ別ランディングページ
  brand/{slug}/index.html    ブランド別ランディングページ
  sitemap.xml                全URL列挙
  robots.txt                 クローラー指示
  index.html                 トップ12商品を静的埋め込み済みに更新

使い方:
  python build_static.py
  python build_static.py --domain https://example.com  # 独自ドメイン指定
"""

import json, re, sys, io, argparse, time
from pathlib import Path
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT   = Path(__file__).parent
DOMAIN = "https://pandora-doj.pages.dev"

# ── CSS（全ページ共通） ──────────────────────────────────────────────
SHARED_CSS = """
:root{--bg:#0a0a0a;--s1:#141414;--s2:#1c1c1c;--border:rgba(255,255,255,.1);
--border2:rgba(255,255,255,.22);--text:#f0f0f0;--muted:#999;--muted2:#ccc;
--accent:#c8f03c;--accent2:#9fc02a;--qc:#38bdf8}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter','Noto Sans JP',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
a{color:inherit;text-decoration:none}
nav{position:sticky;top:0;z-index:200;background:rgba(10,10,10,.97);backdrop-filter:blur(16px);border-bottom:1px solid var(--border)}
.nav-inner{max-width:1200px;margin:0 auto;padding:0 24px;height:58px;display:flex;align-items:center;gap:24px}
.nav-logo{font-family:'Bebas Neue',sans-serif;font-size:24px;letter-spacing:4px;color:var(--accent)}
.nav-link{font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted2);padding:6px 12px;border-radius:6px;border:1px solid var(--border)}
.nav-link:hover{color:var(--accent);border-color:rgba(200,240,60,.3)}
.wrap{max-width:1200px;margin:0 auto;padding:32px 24px 60px}
footer{text-align:center;padding:24px;font-size:11px;color:var(--muted);letter-spacing:1px}
footer a{color:var(--muted2)}
"""

NAV_HTML = """\
<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="/">PANDORA</a>
    <a class="nav-link" href="/catalog.html">全商品</a>
    <a class="nav-link" href="https://www.kakobuy.com/?affcode=a235412" target="_blank" rel="noopener">Kakobuy</a>
  </div>
</nav>"""

FOOTER_HTML = '<footer>PANDORA &nbsp;·&nbsp; <a href="https://www.kakobuy.com/?affcode=a235412" target="_blank" rel="noopener">Kakobuy で購入</a></footer>'

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">'

# ── ユーティリティ ───────────────────────────────────────────────────
def esc(s):
    return str(s or "").replace("&","&amp;").replace('"',"&quot;").replace("<","&lt;").replace(">","&gt;")

def abs_img(img):
    """相対パス 'images/xxx' を '/images/xxx' に変換する"""
    if img and img != "null" and not img.startswith(("http", "/")):
        return "/" + img
    return img or ""

def slugify(s):
    s = re.sub(r"[^\w\s-]", "", str(s or "")).strip()
    return re.sub(r"[\s_-]+", "-", s).lower() or "unknown"

def album_id_from_yupoo(url):
    m = re.search(r"/albums/(\d+)", str(url or ""))
    return m.group(1) if m else None

def clean_title(raw):
    s = str(raw or "").strip()
    # 行頭の価格表記 (+¥165, 209¥ 等) を除去
    s = re.sub(r"^[+\s]*[¥￥]?\s*\d[\d,\.]*\s*[¥￥]?\s*(cny|CNY|rmb|usd|USD|yuan|元)?\s*", "", s)
    s = re.sub(r"^(ON SALE\s*)?[¥￥][\d,.\s]+(cny|CNY|usd|USD)?\s*", "", s, flags=re.IGNORECASE)
    # ブラケット類（【】[]（））をすべて除去
    stripped = re.sub(r"[（【\[][^）\]】]*[）\]】]", "", s)
    stripped = re.sub(r"[一-鿿㐀-䶿]{2,}[^\x00-\x7f]*", "", stripped)
    # 残った単独の価格記号・縦棒を整理
    stripped = re.sub(r"[¥￥][\d,]+|[\d,]+[¥￥]", "", stripped)
    stripped = re.sub(r"\s*[｜|]\s*", " ", stripped)
    stripped = re.sub(r"\s{2,}", " ", stripped).strip().strip("-+").strip()
    if len(stripped) > 2:
        return stripped
    # フォールバック: ブラケット内の最後の有用コンテンツを使用
    inner = re.findall(r"[（【\([]([^）\]】\)]+)[）\]】\)]", s)
    for text in reversed(inner):
        t = re.sub(r"^\s*\d+\s*[¥￥yuan元cny]*\s*$", "", text.strip(), flags=re.IGNORECASE).strip()
        t = re.sub(r"^[A-Z\s]{1,5}$", "", t).strip()
        t = re.sub(r"[｜|]", " ", t)
        t = re.sub(r"\s{2,}", " ", t).strip()
        if len(t) > 2:
            return t
    # 最終フォールバック: 中国語だけ除去
    fb = re.sub(r"[一-鿿㐀-䶿]{2,}[^\x00-\x7f]*", "", raw)
    fb = re.sub(r"\s{2,}", " ", fb).strip()
    return fb or raw[:50]

def fmt_price(p):
    jpy = p.get("price_jpy")
    if jpy and str(jpy) not in ("None","null",""):
        try:
            return f"¥{int(float(str(jpy))):,}"
        except Exception:
            pass
    cny = p.get("price_cny")
    if cny:
        try:
            return f"¥{int(float(str(cny)) * 23.15):,}"
        except Exception:
            pass
    return ""

def card_css():
    return """
a{color:inherit;text-decoration:none}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:20px}
.card{background:var(--s1);border:1px solid var(--border);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
.card:hover{border-color:var(--border2)}
.card-img{width:100%;aspect-ratio:4/3;object-fit:cover;background:var(--s2);display:block}
.card-noimag{width:100%;aspect-ratio:4/3;background:var(--s2);display:flex;align-items:center;justify-content:center;font-size:10px;letter-spacing:1px;color:var(--muted);text-transform:uppercase;font-weight:700}
.card-body{padding:11px;flex:1;display:flex;flex-direction:column;gap:6px}
.card-tags{display:flex;gap:4px;flex-wrap:wrap}
.tag{font-size:9px;font-weight:800;letter-spacing:.8px;text-transform:uppercase;padding:2px 7px;border-radius:999px;border:1px solid var(--border)}
.tag-brand{background:rgba(200,240,60,.1);color:#c8f03c;border-color:rgba(200,240,60,.25)}
.tag-type{background:rgba(255,255,255,.06);color:var(--muted2)}
.card-title{font-size:12px;font-weight:700;color:var(--text);line-height:1.45;flex:1}
.card-price{font-size:14px;font-weight:800;color:var(--accent)}
.card-actions{display:flex;gap:5px}
.btn-buy{flex:1;text-align:center;font-family:'Bebas Neue',sans-serif;font-size:15px;letter-spacing:1.5px;color:#0a0a0a;background:var(--accent);padding:7px 8px;border-radius:6px}
.btn-buy:hover{background:var(--accent2)}
.btn-qc{display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--qc);background:rgba(56,189,248,.1);border:1px solid rgba(56,189,248,.25);padding:7px 9px;border-radius:6px}
"""

def make_card_html(p, link_to_product=True):
    title  = clean_title(p.get("title",""))
    price  = fmt_price(p)
    buy    = esc(p.get("kakobuy") or p.get("purchase") or "#")
    qc     = esc(p.get("yupoo") or "#")
    brand  = esc(p.get("brand",""))
    ptype  = esc(p.get("type",""))
    img    = abs_img(p.get("image",""))
    aid    = album_id_from_yupoo(p.get("yupoo",""))
    prod_url = f"/products/{aid}.html" if aid and link_to_product else None

    if img and len(img) > 4:
        img_html = f'<img class="card-img" src="{esc(img)}" alt="{esc(title)}" loading="lazy">'
    else:
        img_html = '<div class="card-noimag">NO IMAGE</div>'

    if prod_url:
        img_html = f'<a href="{prod_url}">{img_html}</a>'

    title_html = f'<a href="{prod_url}">{esc(title)}</a>' if prod_url else esc(title)

    return f"""<div class="card">
  {img_html}
  <div class="card-body">
    <div class="card-tags">
      {f'<span class="tag tag-brand">{brand}</span>' if brand else ''}
      {f'<span class="tag tag-type">{ptype}</span>' if ptype else ''}
    </div>
    <div class="card-title">{title_html}</div>
    {f'<div class="card-price">{price}</div>' if price else ''}
    <div class="card-actions">
      <a class="btn-buy" href="{buy}" target="_blank" rel="noopener">購入する</a>
      <a class="btn-qc" href="{qc}" target="_blank" rel="noopener">QC</a>
    </div>
  </div>
</div>"""

# ── 1. 商品個別ページ ────────────────────────────────────────────────
def build_product_pages(products, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for p in products:
        aid = album_id_from_yupoo(p.get("yupoo",""))
        if not aid:
            continue
        title  = clean_title(p.get("title",""))
        brand  = p.get("brand","")
        ptype  = p.get("type","")
        price  = fmt_price(p)
        buy    = p.get("kakobuy") or p.get("purchase") or ""
        qc     = p.get("yupoo","")
        img    = abs_img(p.get("image",""))
        desc   = f"{brand} {ptype} レプリカ — {title[:60]}"

        og_img = img if img else ""
        price_val = ""
        if p.get("price_jpy"):
            try: price_val = str(int(float(p["price_jpy"])))
            except: pass

        jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "Product",
            "name": title,
            "brand": {"@type": "Brand", "name": brand},
            "description": desc,
            "image": og_img or "",
            "offers": {
                "@type": "Offer",
                "priceCurrency": "JPY",
                "price": price_val or "0",
                "availability": "https://schema.org/InStock",
                "url": f"{DOMAIN}/products/{aid}.html"
            }
        }, ensure_ascii=False)

        html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | PANDORA</title>
<meta name="description" content="{esc(desc)}">
<meta property="og:title" content="{esc(title)} | PANDORA">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="product">
<meta property="og:url" content="{DOMAIN}/products/{aid}.html">
{f'<meta property="og:image" content="{esc(og_img)}">' if og_img else ''}
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{DOMAIN}/products/{aid}.html">
{FONTS}
<style>{SHARED_CSS}
.product-wrap{{max-width:800px;margin:40px auto;padding:0 24px 60px;display:flex;gap:32px;align-items:flex-start}}
.product-img{{width:380px;flex-shrink:0;border-radius:12px;overflow:hidden;background:var(--s1);border:1px solid var(--border)}}
.product-img img{{width:100%;aspect-ratio:4/3;object-fit:cover;display:block}}
.product-img .noimag{{width:100%;aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px}}
.product-info{{flex:1;min-width:0}}
.product-tags{{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}}
.tag{{font-size:9px;font-weight:800;letter-spacing:.8px;text-transform:uppercase;padding:3px 9px;border-radius:999px;border:1px solid var(--border)}}
.tag-brand{{background:rgba(200,240,60,.1);color:#c8f03c;border-color:rgba(200,240,60,.25)}}
.tag-type{{background:rgba(255,255,255,.06);color:var(--muted2)}}
.product-title{{font-size:20px;font-weight:700;line-height:1.4;margin-bottom:12px;color:var(--text)}}
.product-price{{font-size:28px;font-weight:800;color:var(--accent);margin-bottom:20px;font-family:'Bebas Neue',sans-serif;letter-spacing:1px}}
.btn-primary{{display:block;text-align:center;font-family:'Bebas Neue',sans-serif;font-size:18px;letter-spacing:2px;color:#0a0a0a;background:var(--accent);padding:13px 20px;border-radius:8px;margin-bottom:10px}}
.btn-primary:hover{{background:var(--accent2)}}
.btn-secondary{{display:block;text-align:center;font-size:12px;font-weight:700;color:var(--qc);background:rgba(56,189,248,.1);border:1px solid rgba(56,189,248,.25);padding:10px 20px;border-radius:8px;margin-bottom:24px}}
.back-link{{font-size:12px;color:var(--muted2);}}
.back-link:hover{{color:var(--accent)}}
@media(max-width:640px){{.product-wrap{{flex-direction:column}}.product-img{{width:100%}}}}
</style>
<script type="application/ld+json">{jsonld}</script>
</head>
<body>
{NAV_HTML}
<div class="product-wrap">
  <div class="product-img">
    {f'<img src="{esc(img)}" alt="{esc(title)}" loading="eager">' if img else '<div class="noimag">NO IMAGE</div>'}
  </div>
  <div class="product-info">
    <div class="product-tags">
      {f'<span class="tag tag-brand">{esc(brand)}</span>' if brand else ''}
      {f'<span class="tag tag-type">{esc(ptype)}</span>' if ptype else ''}
    </div>
    <h1 class="product-title">{esc(title)}</h1>
    {f'<div class="product-price">{price}</div>' if price else ''}
    {f'<a class="btn-primary" href="{esc(buy)}" target="_blank" rel="noopener">Kakobuy で購入する</a>' if buy else ''}
    {f'<a class="btn-secondary" href="{esc(qc)}" target="_blank" rel="noopener">QC写真を見る (Yupoo)</a>' if qc else ''}
    <a class="back-link" href="/catalog.html?cat={esc(ptype)}">&larr; {esc(ptype)} を全部見る</a>
  </div>
</div>
{FOOTER_HTML}
</body>
</html>"""
        (out_dir / f"{aid}.html").write_text(html, encoding="utf-8")
        count += 1
    print(f"  [products] {count} ページ生成")
    return count

# ── 2. カテゴリページ ────────────────────────────────────────────────
def build_category_pages(products, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    from collections import defaultdict
    by_cat = defaultdict(list)
    for p in products:
        if p.get("type"):
            by_cat[p["type"]].append(p)

    CAT_DESC = {
        "SNEAKERS":"最新バッチのレプリカスニーカーを網羅。Nike、Jordan、Adidas、New Balanceなど人気モデルを厳選。",
        "HOODIES":"高品質レプリカのパーカー・フーディー。Supreme、Stussy、Palace、Off-Whiteなど。",
        "T-SHIRTS":"レプリカTシャツ。ストリートブランドからラグジュアリーまで幅広く取り揃え。",
        "JACKETS":"レプリカジャケット・コート。秋冬コレクション多数。",
        "PANTS":"レプリカパンツ・スウェット・ジョガーパンツ。",
        "SHORTS":"レプリカショーツ・ショートパンツ。",
        "SWEATERS":"レプリカスウェット・ニット・クルーネック。",
        "TOPS":"レプリカトップス・ベスト・ポロシャツ。",
        "SHIRTS":"レプリカシャツ・フランネル・ワークシャツ。",
        "BAGS":"レプリカバッグ・トート・バックパック。",
        "ACCESSORIES":"レプリカアクセサリー・キャップ・ソックス。",
    }

    count = 0
    for cat, items in by_cat.items():
        slug = slugify(cat)
        cat_dir = out_dir / slug
        cat_dir.mkdir(parents=True, exist_ok=True)
        desc = CAT_DESC.get(cat, f"PANDORAのレプリカ {cat} コレクション。厳選セラーから仕入れた高品質アイテム。")
        featured = [p for p in items if p.get("image") and p["image"]!="null"][:24] or items[:24]
        cards = "\n".join(make_card_html(p) for p in featured)
        jsonld = json.dumps({
            "@context":"https://schema.org","@type":"CollectionPage",
            "name":f"{cat} レプリカ | PANDORA",
            "description":desc,
            "url":f"{DOMAIN}/category/{slug}/"
        }, ensure_ascii=False)
        html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(cat)} レプリカ — 厳選{len(items)}点 | PANDORA</title>
<meta name="description" content="{esc(desc[:150])}">
<meta property="og:title" content="{esc(cat)} レプリカ | PANDORA">
<meta property="og:description" content="{esc(desc[:150])}">
<meta property="og:type" content="website">
<meta property="og:url" content="{DOMAIN}/category/{slug}/">
<link rel="canonical" href="{DOMAIN}/category/{slug}/">
{FONTS}
<style>{SHARED_CSS}{card_css()}
h1{{font-family:'Bebas Neue',sans-serif;font-size:42px;letter-spacing:3px;margin-bottom:6px}}
.sub{{font-size:13px;color:var(--muted2);margin-bottom:4px}}
.more-link{{display:inline-block;margin-top:28px;font-size:12px;font-weight:700;color:var(--accent);border:1px solid rgba(200,240,60,.3);padding:8px 18px;border-radius:6px}}
</style>
<script type="application/ld+json">{jsonld}</script>
</head>
<body>
{NAV_HTML}
<div class="wrap">
  <h1>{esc(cat)}</h1>
  <p class="sub">{esc(desc)}</p>
  <p class="sub">{len(items)}点のアイテム</p>
  <div class="grid">{cards}</div>
  <a class="more-link" href="/catalog.html?cat={esc(cat)}">全{len(items)}点を見る &rarr;</a>
</div>
{FOOTER_HTML}
</body>
</html>"""
        (cat_dir / "index.html").write_text(html, encoding="utf-8")
        count += 1
    print(f"  [category] {count} ページ生成")

# ── 3. ブランドページ ────────────────────────────────────────────────
def build_brand_pages(products, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    from collections import defaultdict
    by_brand = defaultdict(list)
    for p in products:
        if p.get("brand"):
            by_brand[p["brand"]].append(p)

    count = 0
    for brand, items in by_brand.items():
        slug = slugify(brand)
        b_dir = out_dir / slug
        b_dir.mkdir(parents=True, exist_ok=True)
        desc = f"{brand} のレプリカアイテム一覧。PANDORAが厳選したセラーから{len(items)}点を掲載。"
        featured = [p for p in items if p.get("image") and p["image"]!="null"][:24] or items[:24]
        cards = "\n".join(make_card_html(p) for p in featured)
        html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(brand)} レプリカ | PANDORA</title>
<meta name="description" content="{esc(desc[:150])}">
<link rel="canonical" href="{DOMAIN}/brand/{slug}/">
{FONTS}
<style>{SHARED_CSS}{card_css()}
h1{{font-family:'Bebas Neue',sans-serif;font-size:42px;letter-spacing:3px;margin-bottom:6px}}
.sub{{font-size:13px;color:var(--muted2);margin-bottom:4px}}
.more-link{{display:inline-block;margin-top:28px;font-size:12px;font-weight:700;color:var(--accent);border:1px solid rgba(200,240,60,.3);padding:8px 18px;border-radius:6px}}
</style>
</head>
<body>
{NAV_HTML}
<div class="wrap">
  <h1>{esc(brand)}</h1>
  <p class="sub">{esc(desc)}</p>
  <div class="grid">{cards}</div>
  <a class="more-link" href="/catalog.html">&larr; 全カタログへ</a>
</div>
{FOOTER_HTML}
</body>
</html>"""
        (b_dir / "index.html").write_text(html, encoding="utf-8")
        count += 1
    print(f"  [brand] {count} ページ生成")

# ── 4. sitemap.xml ───────────────────────────────────────────────────
def build_sitemap(products, out_path: Path):
    today = time.strftime("%Y-%m-%d")
    urls = [
        f"  <url><loc>{DOMAIN}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>",
        f"  <url><loc>{DOMAIN}/catalog.html</loc><changefreq>daily</changefreq><priority>0.9</priority></url>",
    ]
    # カテゴリ
    cats = {p["type"] for p in products if p.get("type")}
    for cat in sorted(cats):
        urls.append(f'  <url><loc>{DOMAIN}/category/{slugify(cat)}/</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>')
    # ブランド
    brands = {p["brand"] for p in products if p.get("brand")}
    for brand in sorted(brands):
        urls.append(f'  <url><loc>{DOMAIN}/brand/{slugify(brand)}/</loc><changefreq>weekly</changefreq><priority>0.7</priority></url>')
    # 商品
    for p in products:
        aid = album_id_from_yupoo(p.get("yupoo",""))
        if aid:
            urls.append(f'  <url><loc>{DOMAIN}/products/{aid}.html</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>')

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls) + "\n</urlset>"
    out_path.write_text(xml, encoding="utf-8")
    print(f"  [sitemap] {len(urls)} URL → sitemap.xml")

# ── 5. robots.txt ────────────────────────────────────────────────────
def build_robots(out_path: Path):
    out_path.write_text(
        f"User-agent: *\nAllow: /\nSitemap: {DOMAIN}/sitemap.xml\n",
        encoding="utf-8"
    )
    print("  [robots] robots.txt 生成")

# ── 6. index.html にトップ商品を埋め込み ─────────────────────────────
def patch_index(products):
    index_path = ROOT / "index.html"
    if not index_path.exists():
        print("  [index] index.html が見つかりません（スキップ）")
        return

    # カテゴリ別に均等に選んで多様性を確保
    from collections import defaultdict
    CAT_ORDER = ["SNEAKERS","HOODIES","T-SHIRTS","JACKETS","PANTS","SHORTS","SWEATERS","TOPS","SHIRTS","BAGS","ACCESSORIES"]
    by_cat = defaultdict(list)
    for p in products:
        t = p.get("type","")
        if p.get("image") and p["image"] != "null" and p.get("kakobuy") and t:
            by_cat[t].append(p)
    cats_sorted = [c for c in CAT_ORDER if c in by_cat] + [c for c in by_cat if c not in CAT_ORDER]
    featured = []
    # 1周目: カテゴリごとに1件ずつ
    for cat in cats_sorted:
        items = by_cat[cat]
        with_price = [p for p in items if p.get("price_jpy")]
        pool = with_price or items
        if pool:
            featured.append(pool[0])
    # 2周目: 足りない分をカテゴリから追加
    for cat in cats_sorted:
        if len(featured) >= 12:
            break
        items = by_cat[cat]
        with_price = [p for p in items if p.get("price_jpy")]
        pool = (with_price or items)
        if len(pool) > 1:
            featured.append(pool[1])
    featured = featured[:12]
    if not featured:
        print("  [index] 特集商品なし（スキップ）")
        return

    cards = "\n".join(make_card_html(p) for p in featured)
    static_block = f"""
<!-- SSG: 静的埋め込みコンテンツ（SEO用 / JSオフ対応） -->
<section id="static-products" aria-label="注目商品">
<style>
#static-products{{position:relative;z-index:1;max-width:1400px;margin:0 auto;padding:0 24px 48px}}
#static-products h2{{font-family:'Bebas Neue',sans-serif;font-size:28px;letter-spacing:3px;color:var(--muted2);margin-bottom:16px}}
{card_css()}
</style>
<h2>注目商品</h2>
<div class="grid">{cards}</div>
<div style="text-align:center;margin-top:24px">
  <a href="/catalog.html" style="font-size:12px;font-weight:700;color:var(--accent);border:1px solid rgba(200,240,60,.3);padding:10px 24px;border-radius:6px;display:inline-block">全カタログを見る &rarr;</a>
</div>
</section>
<!-- /SSG -->
"""

    content = index_path.read_text(encoding="utf-8")

    # 既存の埋め込みブロックを置換
    content = re.sub(
        r"<!-- SSG:.*?<!-- /SSG -->",
        static_block.strip(),
        content,
        flags=re.DOTALL
    )

    # 初回なら <footer> の直前に挿入
    if "<!-- SSG:" not in content:
        content = content.replace("<footer>", static_block + "\n<footer>", 1)

    index_path.write_text(content, encoding="utf-8")
    print(f"  [index] トップ {len(featured)} 件を index.html に埋め込み")

# ── メイン ──────────────────────────────────────────────────────────
def main():
    global DOMAIN
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default=DOMAIN, help="サイトのドメイン（例: https://example.com）")
    args = parser.parse_args()
    DOMAIN = args.domain.rstrip("/")

    data     = json.loads((ROOT / "products.json").read_text(encoding="utf-8"))
    products = data.get("products", [])
    print(f"[build] {len(products)} 件の商品を処理中... (domain: {DOMAIN})")

    build_product_pages(products, ROOT / "products")
    build_category_pages(products, ROOT / "category")
    build_brand_pages(products, ROOT / "brand")
    build_sitemap(products, ROOT / "sitemap.xml")
    build_robots(ROOT / "robots.txt")
    patch_index(products)

    print(f"\n[build] 完了！")

if __name__ == "__main__":
    main()
