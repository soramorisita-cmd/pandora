# -*- coding: utf-8 -*-
"""
download_images.py
──────────────────
products.json の画像URLをダウンロードして images/ フォルダに保存し、
products.json のパスをローカルパスに書き換えてgit pushする。

使い方:
  python download_images.py
  python download_images.py --no-push
"""

import argparse, hashlib, json, subprocess, time
from pathlib import Path
from urllib.parse import urlparse

import requests

PRODUCTS_JSON = Path(__file__).parent / "products.json"
IMAGES_DIR    = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://www.yupoo.com/",
}

def url_to_filename(url: str) -> str:
    """URLからファイル名を生成（拡張子保持）"""
    parsed = urlparse(url)
    path   = parsed.path  # 例: /angelking47/f2d7270612/medium.jpg
    parts  = path.strip("/").split("/")
    # ハッシュ部分をファイル名に使用
    key    = hashlib.md5(url.encode()).hexdigest()[:10]
    ext    = Path(parts[-1]).suffix or ".jpg"
    return f"{key}{ext}"

def download_image(url: str) -> str | None:
    """画像をダウンロードしてローカルパスを返す"""
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

def git_push(msg: str):
    repo = Path(__file__).parent
    for cmd in [
        ["git", "add", "images/", "products.json"],
        ["git", "commit", "-m", msg],
        ["git", "push"],
    ]:
        r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
        ok = r.returncode == 0 or "nothing to commit" in r.stdout
        print(f"  {'✓' if ok else '⚠'} {' '.join(cmd)}")

async def refetch_missing_images(products: list) -> int:
    """画像URLが空の商品をYupooから再取得する"""
    missing = [(i, p) for i, p in enumerate(products)
               if not p.get("image") or p["image"] in (None, "", "None", "null")]
    if not missing:
        print("✅ 画像なしの商品はありません")
        return 0

    print(f"🔄 画像URL再取得: {len(missing)}件\n")
    refetched = 0

    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

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
                import asyncio
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
    parser.add_argument("--no-push",  action="store_true", help="Git pushをスキップ")
    parser.add_argument("--refetch",  action="store_true", help="画像なし商品をYupooから再取得")
    args = parser.parse_args()

    data     = json.loads(PRODUCTS_JSON.read_text("utf-8"))
    products = data["products"]

    # --refetch: 画像URLが空の商品をYupooから再取得
    if args.refetch:
        import asyncio
        asyncio.run(refetch_missing_images(products))
        # 再取得後にダウンロードへ続く

    # 画像URLがあるものだけダウンロード対象
    targets = [(i, p) for i, p in enumerate(products)
               if p.get("image") and isinstance(p["image"], str)
               and p["image"].startswith("http")]

    if targets:
        print(f"\n🖼  画像ダウンロード: {len(targets)}件\n")
        downloaded = 0
        skipped    = 0

        for n, (i, p) in enumerate(targets, 1):
            url = p["image"]
            print(f"  [{n:03d}/{len(targets)}] {url[30:70]}", end="\r")
            local_path = download_image(url)
            if local_path:
                products[i]["image"] = local_path
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

    if downloaded == 0 and not args.refetch:
        print("（新規ダウンロードなし）")
        return

    if not args.no_push:
        print(f"\n📤 Git push...")
        git_push(f"update product images")
        print(f"\n🌐 約30秒後に反映: https://pandora-doj.pages.dev")
    else:
        print("\n反映するには: git add images/ products.json && git commit -m 'images' && git push")

if __name__ == "__main__":
    main()