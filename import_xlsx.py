# -*- coding: utf-8 -*-
"""
import_xlsx.py
xlsxファイルをdata/*.jsonに変換し、fetch_prices.pyで価格取得後にproducts.jsonへ反映する。

使い方:
  python import_xlsx.py              # data/ 内の全xlsxを処理
  python import_xlsx.py --no-push    # push しない
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json, time, argparse, subprocess
from pathlib import Path
import openpyxl

DATA_DIR      = Path(__file__).parent / "data"
PRODUCTS_JSON = Path(__file__).parent / "products.json"

SELLER_MAP = {
    "2335499519": "2335499519",
}

def xlsx_to_json(xlsx_path: Path) -> dict:
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        return None

    headers = [str(h).strip() if h else "" for h in rows[0]]
    col = {h: i for i, h in enumerate(headers)}

    brand_name = xlsx_path.stem.lstrip('﻿').replace('_', ' ')

    products = []
    for row in rows[1:]:
        if not any(row):
            continue
        yupoo_url = str(row[col.get('YupooURL', 3)] or '').strip()
        if not yupoo_url or yupoo_url == 'None':
            continue

        purchase  = str(row[col.get('TaobaoURL',  4)] or '').strip()
        kakobuy   = str(row[col.get('KakobuyURL', 5)] or '').strip()
        price_cny_raw = row[col.get('価格(CNY)', 6)]
        price_jpy_raw = row[col.get('価格(JPY)', 7)]
        title     = str(row[col.get('アルバムタイトル', 2)] or '').strip()
        ptype     = str(row[col.get('商品タイプ', 1)] or 'Other').strip()

        def parse_price(v):
            if not v or str(v).strip() in ('―', '-', '', 'None'):
                return None
            try:
                return float(str(v).replace(',', '').strip())
            except Exception:
                return None

        # sellerをyupoo URLから抽出
        import re
        m = re.match(r'https?://([^.]+)\.x\.yupoo\.com', yupoo_url)
        seller = m.group(1) if m else '2335499519'

        products.append({
            "title":     title,
            "type":      ptype,
            "yupoo_url": yupoo_url,
            "purchase":  purchase if purchase not in ('None', '') else None,
            "kakobuy":   kakobuy  if kakobuy  not in ('None', '') else None,
            "image":     None,
            "price_cny": parse_price(price_cny_raw),
            "price_jpy": parse_price(price_jpy_raw),
        })

    import re
    m = re.match(r'https?://([^.]+)\.x\.yupoo\.com', products[0]['yupoo_url']) if products else None
    seller = m.group(1) if m else '2335499519'

    return {
        "brand":    brand_name,
        "seller":   seller,
        "updated":  time.strftime("%Y-%m-%dT%H:%M:%S"),
        "products": products,
    }

def load_site_products():
    raw = json.loads(PRODUCTS_JSON.read_text('utf-8'))
    return raw.get('products', raw) if isinstance(raw, dict) else raw

def save_site_products(products, meta=None):
    raw = json.loads(PRODUCTS_JSON.read_text('utf-8'))
    if isinstance(raw, dict):
        raw['products'] = products
        raw['count'] = len(products)
        raw['updated'] = time.strftime("%Y-%m-%dT%H:%M:%S")
        PRODUCTS_JSON.write_text(json.dumps(raw, ensure_ascii=False, indent=2), 'utf-8')
    else:
        PRODUCTS_JSON.write_text(json.dumps(products, ensure_ascii=False, indent=2), 'utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-push', action='store_true')
    args = parser.parse_args()

    xlsx_files = [f for f in DATA_DIR.glob('*.xlsx')
                  if f.stem.lstrip('﻿') not in ('ADIDAS','Balenciaga','Broken_Planet',
                      'Chrome_Hearts','Denim_Tears','ESSENTIALS','HELLSTAR','KITH',
                      'Lacoste','Lanvin','NIKE','Palace','Represent','SUPREME',
                      'Sp5der','Stussy','Syna_World')]

    if not xlsx_files:
        print('処理対象のxlsxファイルがありません')
        return

    print(f'対象ファイル: {[f.name for f in xlsx_files]}')

    new_products = []
    json_paths = []

    for xlsx_path in xlsx_files:
        print(f'\n処理中: {xlsx_path.name}')
        data = xlsx_to_json(xlsx_path)
        if not data:
            print(f'  スキップ（データなし）')
            continue

        print(f'  {data["brand"]}: {len(data["products"])}件')

        json_path = DATA_DIR / (xlsx_path.stem.lstrip('﻿') + '.json')
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
        print(f'  JSON保存: {json_path.name}')
        json_paths.append(json_path)

        for p in data['products']:
            new_products.append({
                'seller':    data['seller'],
                'brand':     data['brand'],
                'type':      p.get('type', 'Other'),
                'title':     p['title'],
                'yupoo':     p['yupoo_url'],
                'purchase':  p.get('purchase') or '',
                'kakobuy':   p.get('kakobuy') or '',
                'image':     p.get('image') or '',
                'price_cny': p.get('price_cny'),
                'price_jpy': p.get('price_jpy'),
                'model':     None,
                'batch':     None,
            })

    if not new_products:
        print('追加商品なし')
        return

    # products.json にマージ（yupoo URLで重複チェック）
    existing = load_site_products()
    existing_yupoos = {p.get('yupoo') for p in existing}
    added = [p for p in new_products if p['yupoo'] not in existing_yupoos]
    print(f'\n新規追加: {len(added)}件 / 重複スキップ: {len(new_products)-len(added)}件')

    if not added:
        print('全て重複のためスキップ')
        return

    merged = existing + added
    save_site_products(merged)
    print(f'products.json 保存完了: {len(merged)}件')

    # fetch_prices.py で価格取得
    print('\n価格取得を開始します...')
    result = subprocess.run(
        ['python', 'fetch_prices.py', '--sync'],
        cwd=Path(__file__).parent
    )

    if result.returncode != 0:
        print('価格取得でエラーが発生しました')

    # build_static.py でビルド
    print('\nビルド中...')
    subprocess.run(['python', 'build_static.py'], cwd=Path(__file__).parent)

    if not args.no_push:
        brands = ', '.join(f.stem.lstrip('﻿') for f in xlsx_files)
        print('\nGit push中...')
        subprocess.run(['git', 'add', 'products.json', 'product-lookup.json',
                        'sitemap.xml', 'index.html', 'brand/', 'category/', 'luxury/'],
                       cwd=Path(__file__).parent)
        subprocess.run(['git', 'commit', '-m', f'feat: add {brands} ({len(added)}件)'],
                       cwd=Path(__file__).parent)
        subprocess.run(['git', 'push'], cwd=Path(__file__).parent)
        print(f'\n反映完了: https://pandora-doj.pages.dev')
    else:
        print('\n--no-push のため push をスキップ')

if __name__ == '__main__':
    main()
