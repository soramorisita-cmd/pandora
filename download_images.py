# -*- coding: utf-8 -*-
"""
download_images.py
──────────────────
products.json の画像URLをダウンロードして images/ フォルダに保存し、
products.json と data/*.json の両方にローカルパスを書き戻してgit pushする。

使い方:
  python download_images.py
  python download_images.py --no-push
  python download_images.py --refetch   # 画像なし商品をYupooから再取得
"""

import argparse, hashlib, json, subprocess, time
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT          = Path(__file__).parent
PRODUCTS_JSON = ROOT / "products.json"
DATA_DIR      = ROOT / "data"
IMAGES_DIR    = ROOT / "images"
IMAGES_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://www.yupoo.com/",
}

def url_to_filename(url: str) -> str:
    key = hashlib.md5(url.encode()).hexdigest()[:10]
    ext = Path(urlparse(url).path).suffix or ".jpg"
    return f"{key}{ext}"

def download_image(url: str) -> str | None:
    fname = url_to_filename(url)
    fpath = IMAGES_DIR / fname
    if fpath.exists():
        return f"images/{fname}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, stream=True)
        if r.status_code == 200:
            fpath.write_bytes(r.content)
            return f"images/{fname}"
        else:
            print(f"  ⚠ HTTP {r.status_code}: {url[:60]}")
            return None
    except Exception as e:
        print(f"  ❌ {e}: {url[:60]}")
        return None

def write_back_to_data(image_map: dict):
    """
    image_map: { yupoo_url: local_image_path }
    yupoo_url はアルバムごとにユニークなのでキーとして使用。
    purchase URL は色違いバリアントで共有されるため使用しない。
    """
    updated_files = 0
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            data     = json.loads(path.read_text("utf-8"))
            products = data.get("products", [])
            changed  = 0
            for p in products:
                # yupoo_url（data/*.json）または yupoo（products.json由来）のみで照合
                key = p.get("yupoo_url") or p.get("yupoo")
                if key and key in image_map:
                    p["image"] = image_map[key]
                    changed += 1
            if changed:
                data["products"] = products
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
                print(f"  💾 {path.name}: {changed}件 書き戻し")
                updated_files += 1
        except Exception as e:
            print(f"  ⚠ {path.name} スキップ: {e}")
    return updated_files

def git_push(msg: str):
    for cmd in [
        ["git", "add", "images/", "products.json", "data/"],
        ["git", "commit", "-m", msg],
        ["git", "push"],
    ]:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        ok = r.returncode == 0 or "nothing to commit" in r.stdout
        print(f"  {'✓' if ok else '⚠'} {' '.join(cmd)}")

async def refetch_missing_images(products: list) -> int:
    missing = [(i, p) for i, p in enumerate(products)
               if not p.get("image") or p["image"] in (None, "", "None", "null")]
    if not missing:
        print("✅ 画像なしの商品はありません")
        return 0

    print(f"🔄 画像URL再取得: {len(missing)}件\n")
    refetched = 0

    from playwright.async_api import async_playwright
    import asyncio

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page    = await browser.new_page()
        await page.set_extra_http_headers({"Accept-Language": "ja,en;q=0.9"})

        for n, (i, p) in enumerate(missing, 1):
            yupoo_url = p.get("yupoo", "")
            if not yupoo_url:
                continue
            print(f"  [{n:03d}/{len(missing)}] {p['title'][:45]}", end="\r")
            try:
                await page.goto(yupoo_url, wait_until="networkidle", timeout=35000)
                await asyncio.sleep(2)
                hrefs = await page.eval_on_selector_all(
                    "img",
                    "els => els.map(e => e.getAttribute('data-src') || e.src || '')"
                )
                for src in hrefs:
                    if src and ("photo.yupoo" in src or "uvd.yupoo" in src):
                        products[i]["image"] = src
                        refetched += 1
                        print(f"  ✅ [{n:03d}] {p['title'][:40]}")
                        break
                else:
                    print(f"  ⚠ [{n:03d}] 画像なし: {p['title'][:40]}")
            except Exception as e:
                print(f"  ❌ [{n:03d}] {e}")
            await asyncio.sleep(0.8)

        await browser.close()

    print(f"\n再取得完了: {refetched}件 / 失敗: {len(missing)-refetched}件")
    return refetched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--refetch", action="store_true")
    args = parser.parse_args()

    data     = json.loads(PRODUCTS_JSON.read_text("utf-8"))
    products = data["products"]

    if args.refetch:
        import asyncio
        asyncio.run(refetch_missing_images(products))

    # 画像URLがあるものをダウンロード
    targets = [(i, p) for i, p in enumerate(products)
               if p.get("image") and isinstance(p["image"], str)
               and p["image"].startswith("http")]

    downloaded = 0
    skipped    = 0
    image_map  = {}  # { url_key: local_path } — data/*.json 書き戻し用

    if targets:
        print(f"\n🖼  画像ダウンロード: {len(targets)}件\n")
        for n, (i, p) in enumerate(targets, 1):
            url = p["image"]
            print(f"  [{n:03d}/{len(targets)}] {url[30:70]}", end="\r")
            local_path = download_image(url)
            if local_path:
                products[i]["image"] = local_path
                # yupoo URL のみをキーに使う（purchase URLは色違いバリアント間で共有されるため不可）
                key = p.get("yupoo") or p.get("yupoo_url")
                if key:
                    image_map[key] = local_path
                downloaded += 1
            else:
                skipped += 1
            time.sleep(0.3)

        print(f"\n✅ ダウンロード完了: {downloaded}件 / スキップ: {skipped}件")
    else:
        downloaded = 0

    # products.json 更新
    data["products"] = products
    data["updated"]  = time.strftime("%Y-%m-%dT%H:%M:%S")
    PRODUCTS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    print(f"💾 products.json 更新完了")

    # data/*.json にも画像パスを書き戻す
    if image_map:
        print(f"\n📂 data/*.json に画像パスを書き戻し中...")
        write_back_to_data(image_map)

    if downloaded == 0 and not args.refetch:
        print("（新規ダウンロードなし）")
        return

    if not args.no_push:
        print(f"\n📤 Git push...")
        git_push("update product images")
        print(f"\n🌐 約30秒後に反映: https://pandora-doj.pages.dev")
    else:
        print("\n反映するには: git add images/ products.json data/ && git commit -m 'images' && git push")

if __name__ == "__main__":
    main()