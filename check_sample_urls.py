import json
from urllib.parse import urlparse, parse_qs

data = json.load(open(r'C:\Users\soram\Desktop\pandora\products.json', encoding='utf-8'))
products = data['products']

# 各プラットフォームのサンプルURL確認
taobao = [p for p in products if 'taobao.com' in p.get('purchase', '')][:2]
weidian_main = [p for p in products if p.get('purchase', '').startswith('https://weidian.com')][:2]
weidian_shop = [p for p in products if '.v.weidian.com' in p.get('purchase', '')][:2]
jadeship = [p for p in products if 'jadeship.com' in p.get('purchase', '')][:2]

print("=== Taobao ===")
for p in taobao:
    url = p['purchase']
    print(f"  URL: {url[:100]}")
    qs = parse_qs(urlparse(url).query)
    print(f"  id: {qs.get('id', ['?'])}")

print("\n=== Weidian (weidian.com) ===")
for p in weidian_main:
    url = p['purchase']
    print(f"  URL: {url[:100]}")
    qs = parse_qs(urlparse(url).query)
    print(f"  itemID: {qs.get('itemID', ['?'])}")

print("\n=== Weidian (shop subdomain) ===")
for p in weidian_shop:
    url = p['purchase']
    print(f"  URL: {url[:100]}")
    qs = parse_qs(urlparse(url).query)
    print(f"  id: {qs.get('id', ['?'])}")

print("\n=== Jadeship ===")
for p in jadeship:
    print(f"  URL: {p['purchase'][:100]}")
