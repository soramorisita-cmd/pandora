import json
from urllib.parse import urlparse
from collections import Counter

data = json.load(open(r'C:\Users\soram\Desktop\pandora\products.json', encoding='utf-8'))
products = data['products']
print(f'総数: {len(products)}')

domains = Counter()
no_purchase = 0
has_price = 0
for p in products:
    url = p.get('purchase', '')
    if not url:
        no_purchase += 1
    else:
        d = urlparse(url).netloc
        domains[d] += 1
    if p.get('price_cny') is not None:
        has_price += 1

print(f'価格あり: {has_price}件')
print(f'購入URLなし: {no_purchase}件')
print('ドメイン別:')
for d, c in domains.most_common():
    print(f'  {d}: {c}件')

print()
for p in products[:3]:
    title = p.get('title', '')[:60]
    purchase = p.get('purchase', '')[:100]
    print(f'title: {title}')
    print(f'purchase: {purchase}')
    print()
