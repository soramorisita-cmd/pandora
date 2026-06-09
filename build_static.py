# -*- coding: utf-8 -*-
"""
build_static.py — PR1 SSG ビルドスクリプト

生成物:
  products/{album_id}.html     個別商品ページ（全件）
  category/{type}/index.html   カテゴリ別ランディングページ
  brand/{slug}/index.html      ブランド別ランディングページ
  data/cat/{type_slug}.json    カテゴリ別分割JSON（PR10 lazy load用）
  data/cats_meta.json          カテゴリ一覧メタ（件数のみ）
  sitemap.xml                  全URL列挙
  robots.txt                   クローラー指示
  _headers                     Cloudflare Cache-Control
  index.html                   トップ12商品を静的埋め込み済みに更新

使い方:
  python build_static.py
  python build_static.py --domain https://example.com  # 独自ドメイン指定
"""

import json, re, sys, io, argparse, time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT   = Path(__file__).parent
DOMAIN = "https://pandora-doj.pages.dev"

# ── CSS（全ページ共通） ──────────────────────────────────────────────
SHARED_CSS = """
:root{--bg:#f0f1f4;--s1:#ffffff;--s2:#f5f6f9;--s3:#e8eaed;--border:rgba(0,0,0,.09);
--border2:rgba(0,0,0,.18);--text:#111111;--muted:#888;--muted2:#555;
--accent:#c8f03c;--accent2:#9fc02a;--accent-dark:#4a7a00;--qc:#0284c7}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'DM Sans','Noto Sans JP',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
a{color:inherit;text-decoration:none}
nav{position:sticky;top:0;z-index:200;background:rgba(255,255,255,.97);backdrop-filter:blur(16px);border-bottom:1px solid var(--border)}
.nav-inner{max-width:1200px;margin:0 auto;padding:0 24px;height:58px;display:flex;align-items:center;gap:16px;overflow-x:auto;scrollbar-width:none}
.nav-inner::-webkit-scrollbar{display:none}
.nav-logo{font-family:'Bebas Neue',sans-serif;font-size:24px;letter-spacing:4px;color:var(--accent-dark);flex-shrink:0}
.nav-link{font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted2);padding:6px 12px;border-radius:6px;border:1px solid var(--border);flex-shrink:0;white-space:nowrap}
.nav-link:hover{color:var(--accent-dark);border-color:rgba(74,122,0,.25)}
.nav-luxury{color:#d4af37!important;border-color:rgba(212,175,55,.35)!important}
.nav-luxury:hover{color:#f0cc5a!important;border-color:rgba(212,175,55,.6)!important}
.wrap{max-width:1200px;margin:0 auto;padding:32px 24px 60px}
footer{text-align:center;padding:24px;font-size:11px;color:var(--muted);letter-spacing:1px}
footer a{color:var(--muted2)}
@media(max-width:600px){
  .nav-inner{gap:6px;padding:0 12px;height:54px}
  .nav-logo{font-size:20px;letter-spacing:3px}
  .nav-link{font-size:10px;padding:5px 9px;letter-spacing:1px}
}
"""

NAV_HTML = """\
<nav>
  <div class="nav-inner">
    <a class="nav-logo" href="/">PANDORA</a>
    <a class="nav-link" href="/catalog.html">全商品</a>
    <a class="nav-link" href="/popular/">人気</a>
    <a class="nav-link nav-luxury" href="/luxury/">LUXURY</a>
    <a class="nav-link" href="/search.html">商品検索</a>
    <a class="nav-link" href="https://www.kakobuy.com/?affcode=a235412" target="_blank" rel="noopener">Kakobuy</a>
  </div>
</nav>"""

FOOTER_HTML = '<footer>PANDORA &nbsp;·&nbsp; <a href="https://www.kakobuy.com/?affcode=a235412" target="_blank" rel="noopener">Kakobuy で購入</a></footer>\n<script src="/click-tracker.js" defer></script>'

CAT_JA = {
    "SNEAKERS": "スニーカー", "HOODIES": "パーカー", "T-SHIRTS": "Tシャツ",
    "JACKETS": "ジャケット", "JEANS": "ジーンズ", "PANTS": "パンツ",
    "SHORTS": "ショーツ", "SWEATERS": "スウェット", "TOPS": "トップス",
    "SHIRTS": "シャツ", "BAGS": "バッグ", "BELTS": "ベルト", "ACCESSORIES": "アクセサリー",
    "HATS": "ハット", "SOCKS": "ソックス", "OTHER": "その他",
    "WALLETS": "財布", "CARDHOLDERS": "カードホルダー",
    "JEWELRY": "ジュエリー", "SCARVES": "スカーフ", "SUNGLASSES": "サングラス",
}

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">'

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

def product_uid(p):
    """商品ページ/ルックアップ用の一意キー。yupoo album_id 優先、無ければ pid（非yupoo商品）。"""
    return album_id_from_yupoo(p.get("yupoo","")) or (p.get("pid") or None)

def qc_link(p):
    """QCボタンのURL。yupooがあればyupoo、無ければUUFinds(qc)。どちらも無ければ空。"""
    return (p.get("yupoo") or "").strip() or (p.get("qc") or "").strip()

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

def fmt_cny(p):
    cny = p.get("price_cny")
    if cny and str(cny) not in ("None","null",""):
        try:
            n = int(float(str(cny)))
            if n > 0:
                return f"{n}元"
        except Exception:
            pass
    return ""

GENDER_FILTER_CSS = """
.gender-bar{display:flex;gap:8px;margin:14px 0 4px;flex-wrap:wrap}
.gf-btn{font-size:10px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;
  padding:5px 14px;border-radius:999px;border:1px solid var(--border);
  background:var(--s1);color:var(--muted2);cursor:pointer;transition:.15s}
.gf-btn:hover{background:var(--s2)}
.gf-btn.active{background:var(--accent);color:#111;border-color:var(--accent2)}
.card.g-hidden{display:none}
.tag-women{background:rgba(236,72,153,.09);color:#be185d;border-color:rgba(236,72,153,.25)}
.tag-men{background:rgba(59,130,246,.09);color:#1d4ed8;border-color:rgba(59,130,246,.25)}
"""

GENDER_FILTER_JS = """<script>
(function(){
  var btns = document.querySelectorAll('.gf-btn');
  btns.forEach(function(btn){
    btn.addEventListener('click', function(){
      btns.forEach(function(b){b.classList.remove('active')});
      this.classList.add('active');
      var g = this.dataset.g;
      document.querySelectorAll('.card').forEach(function(card){
        var cg = card.dataset.gender || '';
        var hide = false;
        if(g === 'all') hide = false;
        else if(g === 'UNISEX') hide = (cg !== '' && cg !== 'UNISEX');
        else hide = (cg !== g);
        card.classList.toggle('g-hidden', hide);
      });
    });
  });
})();
</script>"""

GENDER_FILTER_HTML = """<div class="gender-bar">
  <button class="gf-btn active" data-g="all">ALL</button>
  <button class="gf-btn" data-g="WOMEN">♀ WOMEN</button>
  <button class="gf-btn" data-g="MEN">♂ MEN</button>
  <button class="gf-btn" data-g="UNISEX">UNISEX</button>
</div>"""

def card_css():
    return GENDER_FILTER_CSS + """
a{color:inherit;text-decoration:none}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;margin-top:20px}
.card{background:var(--s1);border:1px solid var(--border);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;transition:border-color .18s,transform .18s,box-shadow .18s;box-shadow:0 1px 4px rgba(0,0,0,.07),0 2px 10px rgba(0,0,0,.04)}
.card:hover{border-color:var(--border2);transform:translateY(-3px);box-shadow:0 6px 24px rgba(0,0,0,.12),0 2px 6px rgba(0,0,0,.06)}
.card-img{width:100%;aspect-ratio:1/1;object-fit:cover;background:var(--s2);display:block}
.card-noimag{width:100%;aspect-ratio:1/1;background:var(--s2);display:flex;align-items:center;justify-content:center;font-size:10px;letter-spacing:1px;color:var(--muted);text-transform:uppercase;font-weight:700}
.card-body{padding:12px;flex:1;display:flex;flex-direction:column;gap:7px}
.card-tags{display:flex;gap:4px;flex-wrap:wrap}
.tag{font-size:10px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;padding:3px 8px;border-radius:999px;border:1px solid var(--border)}
.tag-brand{background:rgba(74,122,0,.08);color:var(--accent-dark);border-color:rgba(74,122,0,.2)}
.tag-type{background:rgba(0,0,0,.05);color:var(--muted2);border-color:rgba(0,0,0,.09)}
.card-title{font-size:13px;font-weight:600;color:var(--muted2);line-height:1.45;flex:1}
.card-price{font-size:17px;font-weight:800;color:var(--accent-dark);letter-spacing:.3px;display:flex;align-items:baseline;gap:5px}
.card-price-cny{font-size:11px;font-weight:600;color:var(--muted);letter-spacing:0}
.card-weight{font-size:11px;color:var(--muted);letter-spacing:0;display:flex;align-items:center;gap:3px}
.card-weight svg{opacity:.55}
.card-actions{display:flex;gap:5px;margin-top:2px}
.btn-buy{flex:1;text-align:center;font-family:'Bebas Neue',sans-serif;font-size:15px;letter-spacing:1.5px;color:#111;background:var(--accent);padding:9px 8px;border-radius:7px}
.btn-buy:hover{background:var(--accent2)}
.btn-qc{display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--qc);background:rgba(2,132,199,.08);border:1px solid rgba(2,132,199,.22);padding:9px 11px;border-radius:7px}
@media(max-width:768px){.grid{grid-template-columns:repeat(2,1fr);gap:10px}.card-title{font-size:12px}.card-price{font-size:15px}.btn-buy{font-size:13px;padding:8px 6px}.btn-qc{padding:8px 9px}}
"""

def make_card_html(p, link_to_product=True):
    title  = clean_title(p.get("title",""))
    price  = fmt_price(p)
    cny    = fmt_cny(p)
    buy    = esc(p.get("kakobuy") or p.get("purchase") or "#")
    qc_url = qc_link(p)
    qc     = esc(qc_url)
    brand  = esc(p.get("brand",""))
    ptype  = esc(p.get("type",""))
    gender = p.get("gender","")
    img    = abs_img(p.get("image",""))
    weight_g  = p.get("weight_g")
    volume_cm = p.get("volume_cm","")
    aid    = product_uid(p)
    prod_url = f"/products/{aid}.html" if aid and link_to_product else None

    if img and len(img) > 4:
        img_html = f'<img class="card-img" src="{esc(img)}" alt="{esc(title)}" loading="lazy">'
    else:
        img_html = '<div class="card-noimag">NO IMAGE</div>'

    if prod_url:
        img_html = f'<a href="{prod_url}">{img_html}</a>'

    title_html = f'<a href="{prod_url}">{esc(title)}</a>' if prod_url else esc(title)
    cny_html   = f'<span class="card-price-cny">/ {cny}</span>' if cny else ''
    if weight_g:
        vol_str = volume_cm.replace("*", "×") if volume_cm else ""
        vol_part = f" · {vol_str}cm" if vol_str else ""
        weight_html = (
            f'<div class="card-weight">'
            f'<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
            f'<path d="M12 2a4 4 0 0 1 4 4H8a4 4 0 0 1 4-4z"/><rect x="3" y="6" width="18" height="15" rx="2"/>'
            f'</svg>{weight_g}g{vol_part}</div>'
        )
    else:
        weight_html = ''

    gender_attr = f' data-gender="{esc(gender)}"' if gender else ''
    gender_tag = ''
    if gender == 'WOMEN':
        gender_tag = '<span class="tag tag-women">♀ Women</span>'
    elif gender == 'MEN':
        gender_tag = '<span class="tag tag-men">♂ Men</span>'

    return f"""<div class="card"{gender_attr}>
  {img_html}
  <div class="card-body">
    <div class="card-tags">
      {f'<span class="tag tag-brand">{brand}</span>' if brand else ''}
      {f'<span class="tag tag-type">{esc(CAT_JA.get(p.get("type",""), ptype))}</span>' if ptype else ''}
      {gender_tag}
    </div>
    <div class="card-title">{title_html}</div>
    {f'<div class="card-price">{price}{cny_html}</div>' if price else ''}
    {weight_html}
    <div class="card-actions">
      <a class="btn-buy" href="{buy}" target="_blank" rel="noopener">Kakobuyで見る →</a>
      {f'<a class="btn-qc" href="{qc}" target="_blank" rel="noopener">QC</a>' if qc_url else ''}
    </div>
  </div>
</div>"""

# ── ラグジュアリーブランド定義 ───────────────────────────────────────
LUXURY_BRANDS = {
    # ファッションハウス
    "Balenciaga", "Gucci", "Dior", "Louis Vuitton", "Celine", "Prada",
    "Hermes", "Moncler", "Lanvin", "Maison Margiela", "Givenchy",
    "Saint Laurent", "Bottega Veneta", "Valentino", "Loewe",
    # ラグジュアリーストリート
    "Off-White", "Amiri", "Purple Brand", "Chrome Hearts", "Vetements",
    "WE11DONE", "Gallery Dept", "Rhude", "Fear of God",
    # コンテンポラリーラグジュアリー
    "Ami Paris", "Jacquemus", "Casablanca", "Acne Studios",
    "A-Cold-Wall*", "Rick Owens",
}

# ── 1. 商品個別ページ ────────────────────────────────────────────────
def build_product_pages(products, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for p in products:
        aid = product_uid(p)
        if not aid:
            continue
        title  = clean_title(p.get("title",""))
        brand  = p.get("brand","")
        ptype  = p.get("type","")
        price  = fmt_price(p)
        buy    = p.get("kakobuy") or p.get("purchase") or ""
        qc     = qc_link(p)
        qc_label = "Yupoo" if (p.get("yupoo") or "").strip() else "UUFinds"
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
.tag-brand{{background:rgba(74,122,0,.08);color:var(--accent-dark);border-color:rgba(74,122,0,.2)}}
.tag-type{{background:rgba(0,0,0,.05);color:var(--muted2);border-color:rgba(0,0,0,.09)}}
.product-title{{font-size:20px;font-weight:700;line-height:1.4;margin-bottom:12px;color:var(--text)}}
.product-price{{font-size:28px;font-weight:800;color:var(--accent-dark);margin-bottom:20px;font-family:'Bebas Neue',sans-serif;letter-spacing:1px}}
.btn-primary{{display:block;text-align:center;font-family:'Bebas Neue',sans-serif;font-size:18px;letter-spacing:2px;color:#111;background:var(--accent);padding:13px 20px;border-radius:8px;margin-bottom:10px}}
.btn-primary:hover{{background:var(--accent2)}}
.btn-secondary{{display:block;text-align:center;font-size:12px;font-weight:700;color:var(--qc);background:rgba(2,132,199,.08);border:1px solid rgba(2,132,199,.22);padding:10px 20px;border-radius:8px;margin-bottom:24px}}
.back-link{{font-size:12px;color:var(--muted2);}}
.back-link:hover{{color:var(--accent-dark)}}
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
    {f'<a class="btn-primary" href="{esc(buy)}" target="_blank" rel="noopener">Kakobuyで見る →</a>' if buy else ''}
    {f'<a class="btn-secondary" href="{esc(qc)}" target="_blank" rel="noopener">QC写真を見る ({qc_label})</a>' if qc else ''}
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
        "JEANS":"レプリカジーンズ・デニムパンツ。Amiri、Purple Brand、Denim Tearsなど人気ブランドを厳選。",
        "PANTS":"レプリカパンツ・スウェット・ジョガーパンツ。",
        "SHORTS":"レプリカショーツ・ショートパンツ。",
        "SWEATERS":"レプリカスウェット・ニット・クルーネック。",
        "TOPS":"レプリカトップス・ベスト・ポロシャツ。",
        "SHIRTS":"レプリカシャツ・フランネル・ワークシャツ。",
        "BAGS":"レプリカバッグ・トート・バックパック。",
        "BELTS":"レプリカベルト。Louis Vuitton・Gucci・Hermesなど高級ブランドのベルトを厳選。",
        "ACCESSORIES":"レプリカアクセサリー・キャップ・ソックス。",
        "WALLETS":"レプリカ財布・長財布・コンパクトウォレット。Louis Vuitton・Dior・Goyardなど。",
        "CARDHOLDERS":"レプリカカードホルダー・カードケース・パスケース。薄型小型のカード収納アイテム。",
        "JEWELRY":"レプリカジュエリー・ネックレス・ブレスレット・リング。",
        "SCARVES":"レプリカスカーフ・ストール・シルクスカーフ。",
        "SUNGLASSES":"レプリカサングラス・アイウェア。",
    }

    count = 0
    for cat, items in by_cat.items():
        slug = slugify(cat)
        cat_dir = out_dir / slug
        cat_dir.mkdir(parents=True, exist_ok=True)
        desc = CAT_DESC.get(cat, f"PANDORAのレプリカ {cat} コレクション。厳選セラーから仕入れた高品質アイテム。")
        items_sorted = sorted(items, key=lambda p: (
            0 if p.get("gender") else 1,
            0 if p.get("price_jpy") else 1,
        ))
        featured = [p for p in items_sorted if p.get("image") and p["image"]!="null"][:24] or items_sorted[:24]
        cards = "\n".join(make_card_html(p) for p in featured)
        has_gender = any(p.get("gender") for p in items)
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
<title>{esc(CAT_JA.get(cat,cat))} レプリカ — 厳選{len(items)}点 | PANDORA</title>
<meta name="description" content="{esc(desc[:150])}">
<meta property="og:title" content="{esc(CAT_JA.get(cat,cat))} レプリカ | PANDORA">
<meta property="og:description" content="{esc(desc[:150])}">
<meta property="og:type" content="website">
<meta property="og:url" content="{DOMAIN}/category/{slug}/">
<link rel="canonical" href="{DOMAIN}/category/{slug}/">
{FONTS}
<style>{SHARED_CSS}{card_css()}
h1{{font-family:'Bebas Neue',sans-serif;font-size:42px;letter-spacing:3px;margin-bottom:6px}}
.sub{{font-size:13px;color:var(--muted2);margin-bottom:4px}}
.more-link{{display:inline-block;margin-top:28px;font-size:12px;font-weight:700;color:var(--accent-dark);border:1px solid rgba(74,122,0,.25);padding:8px 18px;border-radius:6px}}
</style>
<script type="application/ld+json">{jsonld}</script>
</head>
<body>
{NAV_HTML}
<div class="wrap">
  <h1>{esc(CAT_JA.get(cat,cat))}</h1>
  <p class="sub">{esc(desc)}</p>
  <p class="sub">{len(items)}点のアイテム</p>
  {GENDER_FILTER_HTML if has_gender else ''}
  <div class="grid">{cards}</div>
  <a class="more-link" href="/catalog.html?cat={esc(cat)}">全{len(items)}点を見る &rarr;</a>
</div>
{FOOTER_HTML}
{GENDER_FILTER_JS if has_gender else ''}
</body>
</html>"""
        (cat_dir / "index.html").write_text(html, encoding="utf-8")
        count += 1
    print(f"  [category] {count} ページ生成")

# ── 2.5 人気商品ページ /popular/ ──────────────────────────────────────
def build_popular_page(products, out_dir):
    """
    /popular/ - 人気商品ページ
    - /api/popular?limit=100 から動的にデータ取得 (D1 経由)
    - フォールバック: lookup を使って候補商品を出す
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    desc = "PANDORAでクリック数の多い人気商品ランキング。リアルタイム集計（過去のクリック数ベース）。"
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>人気商品ランキング | PANDORA</title>
<meta name="description" content="{esc(desc[:150])}">
<meta property="og:title" content="人気商品ランキング | PANDORA">
<meta property="og:description" content="{esc(desc[:150])}">
<link rel="canonical" href="{DOMAIN}/popular/">
{FONTS}
<style>{SHARED_CSS}{card_css()}
h1{{font-family:'Bebas Neue',sans-serif;font-size:42px;letter-spacing:3px;margin-bottom:6px}}
.sub{{font-size:13px;color:var(--muted2);margin-bottom:4px}}
.rank{{position:absolute;top:8px;left:8px;background:var(--accent);color:#111;font-family:'Bebas Neue',sans-serif;font-size:16px;font-weight:800;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;z-index:2;box-shadow:0 2px 6px rgba(0,0,0,.18)}}
.rank.top1{{background:#FFD700}}
.rank.top2{{background:#C0C0C0}}
.rank.top3{{background:#CD7F32;color:#fff}}
.click-badge{{position:absolute;top:8px;right:8px;background:rgba(0,0,0,.7);color:#fff;font-size:10px;font-weight:700;padding:3px 8px;border-radius:999px;z-index:2}}
.card{{position:relative}}
.empty{{text-align:center;padding:80px 24px;color:var(--muted)}}
.empty h2{{font-size:20px;margin-bottom:12px;color:var(--muted2)}}
</style>
</head>
<body>
{NAV_HTML}
<div class="wrap">
  <h1>人気商品ランキング</h1>
  <p class="sub">クリック数の多い順にTOP100まで表示</p>
  <p class="sub" id="status">読み込み中...</p>
  <div class="grid" id="popular-grid"></div>
</div>
{FOOTER_HTML}
<script>
(async function(){{
  const grid = document.getElementById('popular-grid');
  const status = document.getElementById('status');
  try {{
    const [popRes, lookupRes] = await Promise.all([
      fetch('/api/popular?limit=100'),
      fetch('/data/popular-lookup.json'),
    ]);
    if(!popRes.ok) throw new Error('popular api failed');
    const pop = await popRes.json();
    const byId = await lookupRes.json();

    if(!pop.items || pop.items.length === 0){{
      grid.innerHTML = '<div class="empty" style="grid-column:1/-1"><h2>まだクリックデータがありません</h2><p>カタログから商品を見て、Kakobuy・QCリンクをクリックするとランキングに反映されます。</p></div>';
      status.textContent = '';
      return;
    }}

    status.textContent = '集計件数: ' + pop.items.length + '件';

    let html = '';
    pop.items.forEach((row, idx) => {{
      const id = row.yupoo_id;
      const item = byId[id];
      if(!item) return;
      const rank = idx + 1;
      const rankClass = rank === 1 ? 'top1' : rank === 2 ? 'top2' : rank === 3 ? 'top3' : '';
      const img = item.i || '';
      const img_abs = img.startsWith('http') || img.startsWith('/') ? img : ('/' + img);
      const title = item.t || '';
      const price = item.p ? '¥' + Number(item.p).toLocaleString() : '';
      const buy = item.k || '#';
      const qc = item.y || '#';
      const brand = item.b || '';
      const total = (row.clicks || 0) + (row.qc_clicks || 0);
      html += '<div class="card" data-yupoo="' + id + '">'
        + '<span class="rank ' + rankClass + '">' + rank + '</span>'
        + '<span class="click-badge">' + total + ' pt</span>'
        + (img ? '<img class="card-img" src="' + img_abs + '" alt="" loading="lazy">' : '<div class="card-noimag">NO IMAGE</div>')
        + '<div class="card-body">'
        +   '<div class="card-tags">'
        +     (brand ? '<span class="tag tag-brand">' + brand + '</span>' : '')
        +   '</div>'
        +   '<div class="card-title">' + title + '</div>'
        +   (price ? '<div class="card-price">' + price + '</div>' : '')
        +   '<div class="card-actions">'
        +     '<a class="btn-buy" href="' + buy + '" target="_blank" rel="noopener">Kakobuyで見る →</a>'
        +     '<a class="btn-qc" href="' + qc + '" target="_blank" rel="noopener">QC</a>'
        +   '</div>'
        + '</div>'
        + '</div>';
    }});
    grid.innerHTML = html || '<div class="empty" style="grid-column:1/-1"><h2>表示できる商品がありません</h2></div>';
  }} catch(e) {{
    console.error(e);
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1"><h2>データを取得できませんでした</h2><p>D1データベースが未設定の可能性があります。</p></div>';
    status.textContent = '';
  }}
}})();
</script>
</body>
</html>"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  [popular] /popular/ ページ生成")


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
        items_sorted = sorted(items, key=lambda p: (
            0 if p.get("gender") else 1,
            0 if p.get("price_jpy") else 1,
        ))
        featured = [p for p in items_sorted if p.get("image") and p["image"]!="null"][:24] or items_sorted[:24]
        cards = "\n".join(make_card_html(p) for p in featured)
        has_gender = any(p.get("gender") for p in items)
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
.more-link{{display:inline-block;margin-top:28px;font-size:12px;font-weight:700;color:var(--accent-dark);border:1px solid rgba(74,122,0,.25);padding:8px 18px;border-radius:6px}}
</style>
</head>
<body>
{NAV_HTML}
<div class="wrap">
  <h1>{esc(brand)}</h1>
  <p class="sub">{esc(desc)}</p>
  {GENDER_FILTER_HTML if has_gender else ''}
  <div class="grid">{cards}</div>
  <a class="more-link" href="/catalog.html">&larr; 全カタログへ</a>
</div>
{FOOTER_HTML}
{GENDER_FILTER_JS if has_gender else ''}
</body>
</html>"""
        (b_dir / "index.html").write_text(html, encoding="utf-8")
        count += 1
    print(f"  [brand] {count} ページ生成")

# ── 4. ラグジュアリーページ ──────────────────────────────────────────
def build_luxury_page(products, out_dir):
    from collections import defaultdict
    out_dir.mkdir(parents=True, exist_ok=True)

    luxury_products = [p for p in products if p.get("brand") in LUXURY_BRANDS]
    if not luxury_products:
        print("  [luxury] 対象商品なし（スキップ）")
        return

    by_brand = defaultdict(list)
    for p in luxury_products:
        by_brand[p["brand"]].append(p)

    # ブランドカード HTML
    brand_cards_html = ""
    for brand, items in sorted(by_brand.items(), key=lambda x: -len(x[1])):
        slug = slugify(brand)
        thumb = next((abs_img(p["image"]) for p in items if p.get("image") and p["image"] != "null"), "")
        thumb_html = (f'<img src="{esc(thumb)}" alt="{esc(brand)}" loading="lazy">'
                      if thumb else f'<div class="brand-noimag">{esc(brand)}</div>')
        brand_cards_html += f"""<a class="brand-card" href="/brand/{slug}/">
  <div class="brand-thumb">{thumb_html}</div>
  <div class="brand-info">
    <div class="brand-name">{esc(brand)}</div>
    <div class="brand-count">{len(items)} items</div>
  </div>
</a>"""

    # 注目商品（画像あり・各ブランド1件ずつ最大12件）
    featured = []
    for brand, items in sorted(by_brand.items(), key=lambda x: -len(x[1])):
        pool = [p for p in items if p.get("image") and p["image"] != "null" and p.get("kakobuy")]
        if pool:
            featured.append(pool[0])
        if len(featured) >= 12:
            break
    cards_html = "\n".join(make_card_html(p) for p in featured)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LUXURY — ハイブランドレプリカ | PANDORA</title>
<meta name="description" content="Balenciaga・Off-White・Amiri・Chrome Hearts など厳選ハイブランドのレプリカを掲載。{len(luxury_products)}点のラグジュアリーアイテム。">
<meta property="og:title" content="LUXURY | PANDORA">
<meta property="og:type" content="website">
<meta property="og:url" content="{DOMAIN}/luxury/">
<link rel="canonical" href="{DOMAIN}/luxury/">
{FONTS}
<style>{SHARED_CSS}{card_css()}
:root{{--gold:#d4af37;--gold2:#f0cc5a;--gold-bg:rgba(212,175,55,.08);--gold-border:rgba(212,175,55,.25)}}
.luxury-hero{{background:linear-gradient(160deg,#111 0%,#1a1500 100%);border-bottom:1px solid var(--gold-border);padding:56px 24px 48px;text-align:center}}
.luxury-hero h1{{font-family:'Bebas Neue',sans-serif;font-size:72px;letter-spacing:10px;color:var(--gold);line-height:1}}
.luxury-hero p{{color:var(--muted2);font-size:14px;margin-top:12px;letter-spacing:1px}}
.luxury-hero .total{{display:inline-block;margin-top:16px;font-size:11px;font-weight:700;letter-spacing:2px;color:var(--gold);border:1px solid var(--gold-border);padding:6px 18px;border-radius:999px;background:var(--gold-bg)}}
.section-title{{font-family:'Bebas Neue',sans-serif;font-size:28px;letter-spacing:4px;color:var(--gold);margin:40px 0 16px}}
.brand-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;margin-bottom:48px}}
.brand-card{{background:var(--s1);border:1px solid var(--gold-border);border-radius:10px;overflow:hidden;display:flex;flex-direction:column;transition:border-color .2s}}
.brand-card:hover{{border-color:var(--gold)}}
.brand-thumb{{aspect-ratio:4/3;overflow:hidden;background:var(--s2)}}
.brand-thumb img{{width:100%;height:100%;object-fit:cover;display:block}}
.brand-noimag{{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:800;letter-spacing:1px;color:var(--gold);text-transform:uppercase;text-align:center;padding:8px}}
.brand-info{{padding:10px 12px}}
.brand-name{{font-size:12px;font-weight:800;letter-spacing:.5px;color:var(--text)}}
.brand-count{{font-size:10px;color:var(--gold);margin-top:3px;font-weight:600}}
.tag-brand{{background:rgba(212,175,55,.1);color:var(--gold);border-color:var(--gold-border)}}
</style>
</head>
<body>
{NAV_HTML}
<div class="luxury-hero">
  <h1>LUXURY</h1>
  <p>厳選ハイブランド・レプリカコレクション</p>
  <span class="total">{len(luxury_products)} ITEMS · {len(by_brand)} BRANDS</span>
</div>
<div class="wrap">
  <div class="section-title">BRANDS</div>
  <div class="brand-grid">{brand_cards_html}</div>
  <div class="section-title">FEATURED</div>
  <div class="grid">{cards_html}</div>
  <div style="text-align:center;margin-top:28px">
    <a href="/catalog.html" style="font-size:12px;font-weight:700;color:var(--gold);border:1px solid var(--gold-border);padding:10px 24px;border-radius:6px;display:inline-block">全カタログを見る &rarr;</a>
  </div>
</div>
{FOOTER_HTML}
</body>
</html>"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  [luxury] {len(by_brand)} ブランド / {len(luxury_products)} 件")

# ── 5. sitemap.xml ───────────────────────────────────────────────────
def build_sitemap(products, out_path: Path):
    today = time.strftime("%Y-%m-%d")
    urls = [
        f"  <url><loc>{DOMAIN}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>",
        f"  <url><loc>{DOMAIN}/catalog.html</loc><changefreq>daily</changefreq><priority>0.9</priority></url>",
        f"  <url><loc>{DOMAIN}/luxury/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>",
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
    CAT_ORDER = ["SNEAKERS","HOODIES","T-SHIRTS","JACKETS","JEANS","PANTS","SHORTS","SWEATERS","TOPS","SHIRTS","BAGS","WALLETS","CARDHOLDERS","BELTS","ACCESSORIES"]
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

# ── 7. カテゴリ別JSON分割（PR10: lazy load用） ──────────────────────
def split_products_json(products, updated):
    """
    data/cat/{type_slug}.json を生成する。
    catalog.html が ?cat=TYPE の時だけこれをフェッチ → 初回転送量を大幅削減。
    - purchase フィールドは kakobuy と重複するため除外（-9% サイズ）
    - price_cny も除外（price_jpy に変換済み）
    """
    from collections import defaultdict
    cat_dir = ROOT / "data" / "cat"
    cat_dir.mkdir(parents=True, exist_ok=True)

    EXCLUDE = {"purchase", "price_cny"}
    by_cat = defaultdict(list)
    for p in sorted(products, key=lambda p: 0 if p.get("price_jpy") else 1):
        cat = p.get("type") or "other"
        slim = {k: v for k, v in p.items() if k not in EXCLUDE}
        by_cat[cat].append(slim)

    sizes = []
    for cat, items in by_cat.items():
        slug = cat.lower().replace("-", "_").replace(" ", "_")
        payload = json.dumps(
            {"type": cat, "count": len(items), "updated": updated, "products": items},
            ensure_ascii=False, separators=(',', ':')
        )
        out_path = cat_dir / f"{slug}.json"
        out_path.write_text(payload, encoding="utf-8")
        sizes.append((cat, len(items), len(payload) // 1024))

    # カテゴリ一覧メタ（件数のみ、nav 描画用）
    CAT_ORDER = ["SNEAKERS","HOODIES","T-SHIRTS","JACKETS","JEANS","PANTS","SHORTS",
                 "SWEATERS","TOPS","SHIRTS","BAGS","WALLETS","CARDHOLDERS","BELTS","ACCESSORIES"]
    sorted_cats = (
        [c for c in CAT_ORDER if c in by_cat] +
        sorted(c for c in by_cat if c not in CAT_ORDER)
    )
    cats_meta = [{"type": c, "count": len(by_cat[c]), "slug": c.lower().replace("-","_").replace(" ","_")} for c in sorted_cats]
    (ROOT / "data" / "cats_meta.json").write_text(
        json.dumps({"total": len(products), "categories": cats_meta}, ensure_ascii=False, separators=(',', ':')),
        encoding="utf-8"
    )

    print(f"  [split] {len(by_cat)} カテゴリ → data/cat/")
    for cat, cnt, kb in sorted(sizes, key=lambda x: -x[1])[:5]:
        print(f"    {cat}: {cnt}件 / {kb}KB")


def build_headers():
    """Cloudflare Pages 用 _headers（Cache-Control）"""
    headers = """\
# Cloudflare Pages Cache-Control
/catalog.html
  Cache-Control: no-cache, must-revalidate
/index.html
  Cache-Control: no-cache, must-revalidate
/products.json
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400
/data/*.json
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400
/data/cat/*.json
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400
/products/*.html
  Cache-Control: public, max-age=86400, stale-while-revalidate=604800
/images/*
  Cache-Control: public, max-age=2592000
/category/*
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400
/brand/*
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400
/luxury/*
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400
"""
    (ROOT / "_headers").write_text(headers, encoding="utf-8")
    print("  [headers] _headers 生成完了")


# ── 商品ルックアップJSON生成 ────────────────────────────────────────────
def generate_lookup_json(products: list):
    by_album = {}
    by_item  = {}
    for p in products:
        row = [
            p.get("title", "")[:80],
            p.get("brand", ""),
            p.get("type", ""),
            p.get("image", ""),
            p.get("price_cny") or "",
            p.get("price_jpy") or "",
            p.get("weight_g") or "",
            p.get("volume_cm") or "",
            p.get("kakobuy") or "",
            p.get("purchase") or "",
        ]
        yupoo = p.get("yupoo", "")
        if yupoo:
            m = re.search(r'/albums?/(\d+)', yupoo)
            if m:
                by_album[m.group(1)] = row
        purchase = p.get("purchase", "")
        if purchase:
            try:
                parsed = urlparse(purchase)
                qs     = parse_qs(parsed.query)
                netloc = parsed.netloc.lower()
                if "weidian.com" in netloc:
                    item_id = (qs.get("itemID") or qs.get("id") or [None])[0]
                    if item_id:
                        by_item[item_id] = row
                elif "taobao.com" in netloc or "tmall.com" in netloc:
                    item_id = qs.get("id", [None])[0]
                    if item_id:
                        by_item[item_id] = row
                elif "jadeship.com" in netloc:
                    # jadeship universal link: /item/{weidian|taobao|1688}/{id}
                    m = re.search(r'/item/(?:weidian|taobao|1688)/(\w+)', parsed.path)
                    if m:
                        by_item[m.group(1)] = row
            except Exception:
                pass
    lookup = {"a": by_album, "i": by_item}
    out_path = ROOT / "product-lookup.json"
    out_path.write_text(json.dumps(lookup, ensure_ascii=False, separators=(",", ":")), "utf-8")

    # /popular/ ページ用の軽量lookup（album_id → 商品データ）
    pop_lookup = {}
    for p in products:
        yupoo = p.get("yupoo", "")
        m = re.search(r'/albums?/(\d+)', yupoo)
        if not m:
            continue
        pop_lookup[m.group(1)] = {
            "t": (p.get("title","") or "")[:80],
            "b": p.get("brand","") or "",
            "i": p.get("image","") or "",
            "p": p.get("price_jpy"),
            "k": p.get("kakobuy","") or "",
            "y": yupoo,
        }
    (ROOT / "data" / "popular-lookup.json").write_text(
        json.dumps(pop_lookup, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8"
    )
    print(f"  [popular-lookup] {len(pop_lookup)} items → data/popular-lookup.json")
    print(f"  [lookup] {len(by_album)} albums / {len(by_item)} items → product-lookup.json")


# ── メイン ──────────────────────────────────────────────────────────
def main():
    global DOMAIN
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default=DOMAIN, help="サイトのドメイン（例: https://example.com）")
    args = parser.parse_args()
    DOMAIN = args.domain.rstrip("/")

    data     = json.loads((ROOT / "products.json").read_text(encoding="utf-8"))
    products = data.get("products", [])

    # Taobao購入リンクがあるが価格未取得の商品は除外（削除済みリスティング）
    def _is_taobao(url: str) -> bool:
        return bool(url) and "taobao.com" in urlparse(url).netloc.lower()
    before = len(products)
    products = [
        p for p in products
        if not (_is_taobao(p.get("purchase", "")) and not p.get("price_jpy"))
    ]
    print(f"[build] {len(products)} 件の商品を処理中... (domain: {DOMAIN})")
    print(f"  (Taobao削除済み除外: {before - len(products)} 件)")

    build_product_pages(products, ROOT / "products")
    build_category_pages(products, ROOT / "category")
    build_brand_pages(products, ROOT / "brand")
    build_luxury_page(products, ROOT / "luxury")
    build_popular_page(products, ROOT / "popular")
    build_sitemap(products, ROOT / "sitemap.xml")
    build_robots(ROOT / "robots.txt")
    split_products_json(products, data.get("updated", ""))
    build_headers()
    patch_index(products)
    generate_lookup_json(products)

    # products.json をminify化（モバイルロード高速化）
    pjson_path = ROOT / "products.json"
    pjson_path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(',', ':')),
        encoding="utf-8"
    )
    size_mb = pjson_path.stat().st_size / 1024 / 1024
    print(f"  [minify] products.json: {size_mb:.1f} MB")

    print(f"\n[build] 完了！")

if __name__ == "__main__":
    main()
