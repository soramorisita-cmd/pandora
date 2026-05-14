import sys, io, re, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import json
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright

TITLE_PRICE_RE = re.compile(
    r'[【\[]\s*(\d+(?:\.\d+)?)\s*(?:yuan|cny|rmb|元|￥|¥)\s*[】\]]',
    re.IGNORECASE,
)
PRICE_RE = re.compile(r'¥\s*([\d]+(?:\.[\d]+)?)')

data = json.load(open(r'C:\Users\soram\Desktop\pandora\products.json', encoding='utf-8'))
products = data['products']

# タイトル価格のない商品を各プラットフォームから5件ずつ選ぶ
def get_samples():
    samples = {'weidian': [], 'taobao': [], 'jadeship': []}
    for p in products:
        if TITLE_PRICE_RE.search(p.get('title', '')):
            continue
        if not p.get('purchase'):
            continue
        host = urlparse(p['purchase']).netloc.lower()
        pf = ('weidian' if 'weidian.com' in host
              else 'taobao' if 'taobao.com' in host
              else 'jadeship' if 'jadeship.com' in host
              else None)
        if pf and len(samples[pf]) < 3:
            samples[pf].append(p)
    return samples

def parse_price(html: str):
    for m in PRICE_RE.finditer(html):
        v = float(m.group(1))
        if 1 < v < 100_000:
            return v
    return None

def weidian_id(url):
    qs = parse_qs(urlparse(url).query)
    return (qs.get('itemID') or qs.get('id') or [None])[0]

def taobao_id(url):
    return parse_qs(urlparse(url).query).get('id', [None])[0]

async def main():
    samples = get_samples()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for pf, items in samples.items():
            print(f"\n=== {pf} ({len(items)} samples) ===")
            for p in items:
                url = p['purchase']
                if pf == 'weidian':
                    iid = weidian_id(url)
                    target = f"https://weidian.com/item.html?itemID={iid}"
                elif pf == 'taobao':
                    iid = taobao_id(url)
                    target = f"https://h5.m.taobao.com/awp/core/detail.htm?id={iid}"
                else:
                    target = url

                ctx = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    locale="zh-CN",
                )
                page = await ctx.new_page()
                try:
                    await page.goto(target, wait_until="networkidle", timeout=30000)
                    await asyncio.sleep(2)
                    html = await page.content()
                    price = parse_price(html)
                    print(f"  [{pf}] {p['title'][:45]:45} -> {price} CNY")
                except Exception as e:
                    print(f"  [{pf}] {p['title'][:45]:45} -> ERROR: {str(e)[:40]}")
                finally:
                    await page.close()
                    await ctx.close()

        await browser.close()

asyncio.run(main())
