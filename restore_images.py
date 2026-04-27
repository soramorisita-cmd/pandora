# -*- coding: utf-8 -*-
"""
restore_images.py
─────────────────
old_products.json の image パスを data/*.json に還元する。

使い方:
  python restore_images.py                        # old_products.json から復元
  python restore_images.py --src some_backup.json # 別ファイルから復元
"""

import argparse, json
from pathlib import Path

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="old_products.json")
    args = parser.parse_args()

    src = ROOT / args.src
    if not src.exists():
        print(f"❌ {src} が見つかりません")
        print("先に: git show HEAD~1:products.json > old_products.json")
        return

    old = json.loads(src.read_text("utf-8"))
    old_products = old.get("products", [])

    # yupoo URL or kakobuy URL をキーに画像パスを引く
    image_map = {}
    for p in old_products:
        img = p.get("image")
        if not img:
            continue
        key = p.get("yupoo") or p.get("kakobuy") or p.get("purchase")
        if key:
            image_map[key] = img

    print(f"📦 旧データ: {len(old_products)}件 / 画像あり: {len(image_map)}件")

    total_restored = 0
    total_missing  = 0

    for path in sorted(DATA_DIR.glob("*.json")):
        data     = json.loads(path.read_text("utf-8"))
        products = data.get("products", [])
        restored = 0

        for p in products:
            if p.get("image"):  # すでに画像があればスキップ
                continue
            key = p.get("yupoo") or p.get("kakobuy") or p.get("purchase")
            if key and key in image_map:
                p["image"] = image_map[key]
                restored += 1

        missing = sum(1 for p in products if not p.get("image"))
        data["products"] = products
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

        print(f"  ✓ {path.name}: {restored}件復元 / 画像なし残り {missing}件")
        total_restored += restored
        total_missing  += missing

    print(f"\n✅ 合計 {total_restored}件の画像パスを復元")
    if total_missing:
        print(f"⚠  {total_missing}件は旧データにも画像なし → download_images.py --refetch で再取得できます")

    print("\n次のステップ:")
    print("  python merge_data.py")

if __name__ == "__main__":
    main()
