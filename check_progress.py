import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

data = json.load(open(r'C:\Users\soram\Desktop\pandora\products.json', encoding='utf-8'))
products = data['products']

with_price = [p for p in products if p.get('price_cny') is not None]
without_price = [p for p in products if p.get('price_cny') is None and p.get('purchase')]

print(f"総数: {len(products)}")
print(f"価格あり: {len(with_price)}")
print(f"価格なし(購入URL有): {len(without_price)}")

# サンプル表示
print("\n価格あり サンプル:")
for p in with_price[:5]:
    print(f"  {p.get('title','')[:50]:50} -> {p['price_cny']} CNY / {p.get('price_jpy')} JPY")

print("\n価格なし サンプル（次に取得する商品）:")
from urllib.parse import urlparse
for p in without_price[:5]:
    host = urlparse(p.get('purchase', '')).netloc
    print(f"  [{host}] {p.get('title','')[:50]}")
