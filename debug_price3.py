import sys, io, re, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests

# Taobao: Jadeship経由を試す
TAOBAO_ID = "887785056459"
url = f"https://www.jadeship.com/item/taobao/{TAOBAO_ID}"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
r = requests.get(url, headers=headers, timeout=15)
print(f"Jadeship/Taobao status: {r.status_code} url: {r.url}")
text = r.text
for pat in [
    r'"price"\s*:\s*"?([\d]+\.?\d*)"?',
    r'¥\s*([\d]+\.?\d*)',
    r'CNY\s*([\d]+\.?\d*)',
    r'"currentPrice"\s*:\s*([\d]+\.?\d*)',
]:
    m = re.findall(pat, text)
    if m:
        print(f"  {pat[:40]}: {m[:5]}")

# タイトルから価格を抽出（フォールバック）
print("\n=== タイトルから価格パターンを確認 ===")
import json
data = json.load(open(r'C:\Users\soram\Desktop\pandora\products.json', encoding='utf-8'))
products = data['products']

title_price_count = 0
for p in products[:200]:
    title = p.get('title', '')
    m = re.search(r'[【\[]\s*(\d+)\s*yuan\s*[】\]]', title, re.IGNORECASE)
    if m:
        title_price_count += 1

all_yuan = sum(1 for p in products if re.search(r'[【\[]\s*\d+\s*yuan\s*[】\]]', p.get('title',''), re.IGNORECASE))
print(f"タイトルに価格(yuan)があるもの: {all_yuan}/{len(products)} ({100*all_yuan//len(products)}%)")

# サンプル表示
for p in products[:5]:
    title = p.get('title','')
    m = re.search(r'[【\[]\s*(\d+)\s*yuan\s*[】\]]', title, re.IGNORECASE)
    if m:
        print(f"  価格: {m.group(1)} CNY | {title[:60]}")
