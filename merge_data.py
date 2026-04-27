# -*- coding: utf-8 -*-
"""
merge_data.py
─────────────
data/*.json を統合して products.json を生成し、git push する。
既存 products.json の image パスを yupoo/kakobuy URL で照合して引き継ぐ。

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
    """既存 products.json から {url: image_path} のマップを作る"""
    if not OUTPUT_FILE.exists():
        return {}
    try:
        old = json.loads(OUTPUT_FILE.read_text("utf-8"))
    except Exception:
        return {}
    image_map = {}
    for p in old.get("products", []):
        img = p.get("image")
        if not img:
            continue
        for key_field in ("yupoo", "kakobuy", "purchase"):
            key = p.get(key_field)
            if key:
                image_map[key] = img
    return image_map

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
            products = data.get("products", [])
            restored = 0
            for p in products:
                if not p.get("image"):
                    for key_field in ("yupoo", "kakobuy", "purchase"):
                        key = p.get(key_field)
                        if key and key in image_map:
                            p["image"] = image_map[key]
                            restored += 1
                            break
            all_products.extend(products)
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
        ["git", "add", "data/", "products.json"],
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