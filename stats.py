import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from urllib.parse import urlparse

TITLE_PRICE_RE = re.compile(
    r'[【\[]\s*(\d+(?:\.\d+)?)\s*(?:yuan|cny|rmb|元|￥|¥)\s*[】\]]',
    re.IGNORECASE,
)

data = json.load(open(r'C:\Users\soram\Desktop\pandora\products.json', encoding='utf-8'))
products = data['products']

has_price = sum(1 for p in products if p.get('price_cny') is not None)
title_priceable = sum(1 for p in products
    if p.get('price_cny') is None
    and TITLE_PRICE_RE.search(p.get('title',''))
)
need_playwright = []
for p in products:
    if p.get('price_cny') is not None: continue
    if TITLE_PRICE_RE.search(p.get('title','')): continue
    if not p.get('purchase'): continue
    host = urlparse(p['purchase']).netloc.lower()
    pf = ('weidian' if 'weidian.com' in host
          else 'taobao' if 'taobao.com' in host
          else 'jadeship' if 'jadeship.com' in host
          else 'other')
    need_playwright.append(pf)

from collections import Counter
pf_count = Counter(need_playwright)

print(f"総数:                {len(products)}")
print(f"価格取得済み:         {has_price}")
print(f"タイトル取得可能:      {title_priceable}")
print(f"Playwright必要:       {len(need_playwright)}")
print(f"  内訳: {dict(pf_count)}")
