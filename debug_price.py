import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests, re

item_id = "7488912496"
url = f"https://weidian.com/item.html?itemID={item_id}"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://weidian.com/",
}

r = requests.get(url, headers=headers, timeout=15)
print(f"Status: {r.status_code}")
print(f"Content-Type: {r.headers.get('Content-Type','')}")
print(f"Final URL: {r.url}")
print(f"Content length: {len(r.text)}")
print()

# 価格っぽいパターンを全て表示
text = r.text
for pat in [r'"price"[^}]{0,50}', r'"itemPrice"[^}]{0,50}', r'"skuPrice"[^}]{0,50}',
            r'[\d]+\.[\d]+ ?yuan', r'¥[\d.]+']:
    matches = re.findall(pat, text)
    if matches:
        print(f"Pattern [{pat[:30]}]: {matches[:5]}")

# スクリプトタグ内のJSONを確認
import re
scripts = re.findall(r'<script[^>]*>(.*?)</script>', text, re.DOTALL)
print(f"\nScript tags: {len(scripts)}")
for i, s in enumerate(scripts):
    if 'price' in s.lower() and len(s) < 5000:
        print(f"\n--- script[{i}] ({len(s)} chars) ---")
        print(s[:500])
