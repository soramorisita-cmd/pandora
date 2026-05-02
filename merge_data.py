# -*- coding: utf-8 -*-
"""
merge_data.py
─────────────
data/*.json を統合して products.json を生成し、git push する。
・yupoo_url → yupoo にリネーム
・brand / seller をファイルレベルから各商品に付与
・既存 products.json の image パスを引き継ぐ

使い方:
  python merge_data.py           # マージ + git push
  python merge_data.py --no-push # マージのみ（確認用）
"""

import argparse, json, subprocess, time
from pathlib import Path

ROOT        = Path(__file__).parent
DATA_DIR    = ROOT / "data"
OUTPUT_FILE = ROOT / "products.json"

def build_image_map():
    """
    既存 products.json から照合マップを作る。
    キー1: yupoo URL（アルバムURLはユニーク）
    キー2: http画像URL自体（yupoo照合が失敗した場合のフォールバック）
    値: ローカル画像パス（images/xxxx.jpg）
    """
    if not OUTPUT_FILE.exists():
        return {}
    try:
        old = json.loads(OUTPUT_FILE.read_text("utf-8"))
    except Exception:
        return {}
    image_map = {}
    for p in old.get("products", []):
        img = p.get("image")
        if not img or not img.startswith("images/"):
            continue  # ローカルパスのみ対象
        # キー1: yupoo URL
        key = p.get("yupoo") or p.get("yupoo_url")
        if key:
            image_map[key] = img
    # キー2: data/*.json の http画像URL → ローカルパス のマップも追加
    # download_images.py がダウンロード済みのファイル名から逆引き
    import hashlib
    from urllib.parse import urlparse
    images_dir = ROOT / "images"
    for p in old.get("products", []):
        # products.json 上でローカルパスになっている場合、
        # data/*.json 側はまだ http:// の可能性があるので
        # ファイル名のMD5ハッシュから元URLを特定するのは不可能
        # → download_images.py 側で解決済みなのでここでは yupoo キーのみ
        pass
    return image_map

def normalize_product(p: dict, brand: str, seller: str, image_map: dict) -> dict:
    """data/*.json の商品を products.json 用フォーマットに変換"""
    yupoo = p.get("yupoo") or p.get("yupoo_url") or ""
    img   = p.get("image") or ""
    out = {
        "seller":    p.get("seller")    or seller,
        "brand":     p.get("brand")     or brand,
        "type":      p.get("type")      or "Other",
        "title":     p.get("title")     or "",
        "yupoo":     yupoo,
        "purchase":  p.get("purchase")  or "",
        "kakobuy":   p.get("kakobuy")   or "",
        "image":     img,
        "price_cny": p.get("price_cny"),
        "price_jpy": p.get("price_jpy"),
        "model":     p.get("model")     or None,
        "batch":     p.get("batch")     or None,
    }
    # 画像がローカルパスなら保持、http:// または空なら image_map から引き継ぐ
    if not img.startswith("images/"):
        if yupoo and yupoo in image_map:
            out["image"] = image_map[yupoo]
        # それでも http:// のままなら空にしてサイトで壊れた画像を出さない
        # （download_images.py --refetch で補完可能）
    return out

def merge():
    image_map = build_image_map()
    print(f"🖼  既存画像パス: {len(image_map)}件 引き継ぎ対象")

    all_products = []
    files_loaded = []

    json_files = sorted(DATA_DIR.glob("*.json"))
    if not json_files:
        print(f"❌ {DATA_DIR} にJSONファイルが見つかりません")
        return False

    for path in json_files:
        try:
            data     = json.loads(path.read_text("utf-8"))
            brand    = data.get("brand")  or path.stem
            seller   = data.get("seller") or ""
            products = data.get("products", [])

            normalized = [normalize_product(p, brand, seller, image_map) for p in products]
            restored   = sum(1 for p, n in zip(products, normalized)
                             if not p.get("image") and n.get("image"))

            all_products.extend(normalized)
            files_loaded.append(
                f"  ✓ {path.name:30s} {len(products):4d}件"
                + (f"  (画像復元 {restored}件)" if restored else "")
            )
        except Exception as e:
            print(f"  ⚠ {path.name} スキップ: {e}")

    print(f"\n📂 読み込み完了:")
    for line in files_loaded:
        print(line)

    out = {
        "updated":  time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count":    len(all_products),
        "products": all_products,
    }
    OUTPUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")

    with_img    = sum(1 for p in all_products if p.get("image"))
    without_img = len(all_products) - with_img
    print(f"\n✅ products.json 生成: {len(all_products)}件")
    print(f"   画像あり: {with_img}件 / 画像なし: {without_img}件")
    if without_img:
        print(f"   → 画像なし商品は: python download_images.py --refetch で補完できます")
    return True

def git_push():
    for cmd in [
        ["git", "add", "data/", "products.json", "images/", "index.html", "catalog.html", "converter.html"],
        ["git", "commit", "-m", "merge: update products.json"],
        ["git", "push"],
    ]:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        ok = r.returncode == 0 or "nothing to commit" in r.stdout
        print(f"  {'✓' if ok else '⚠'} {' '.join(cmd)}")
        if not ok and r.stderr.strip():
            print(f"    {r.stderr.strip()}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()

    success = merge()
    if not success:
        return

    if args.no_push:
        print("\n（--no-push のため git push をスキップ）")
        return

    print(f"\n📤 Git push...")
    git_push()
    print(f"\n🌐 約30秒後に反映: https://pandora-doj.pages.dev")

if __name__ == "__main__":
    main()