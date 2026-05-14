# -*- coding: utf-8 -*-
"""
cleanup_images.py
─────────────────
data/*.json に参照されていない images/ の孤立画像を削除する。

使い方:
  python cleanup_images.py          # 確認してから削除
  python cleanup_images.py --dry-run # 削除せずに一覧表示のみ
"""

import argparse, json
from pathlib import Path

ROOT       = Path(__file__).parent
DATA_DIR   = ROOT / "data"
IMAGES_DIR = ROOT / "images"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="削除せず一覧表示のみ")
    args = parser.parse_args()

    # data/*.json から参照されている画像ファイル名を収集
    referenced = set()
    for path in DATA_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text("utf-8"))
            for p in data.get("products", []):
                img = p.get("image", "")
                if img and img.startswith("images/"):
                    referenced.add(img.replace("images/", ""))
        except Exception as e:
            print(f"⚠ {path.name} スキップ: {e}")

    print(f"📦 参照中の画像: {len(referenced)}件")

    # images/ フォルダの全ファイルと比較
    all_images = list(IMAGES_DIR.iterdir()) if IMAGES_DIR.exists() else []
    orphans = [f for f in all_images if f.is_file() and f.name not in referenced]

    if not orphans:
        print("✅ 孤立画像はありません")
        return

    total_size = sum(f.stat().st_size for f in orphans) / 1024 / 1024
    print(f"🗑  孤立画像: {len(orphans)}件 ({total_size:.1f} MB)")

    if args.dry_run:
        print("\n--- 削除対象（--dry-run）---")
        for f in orphans:
            print(f"  {f.name}")
        return

    confirm = input(f"\n{len(orphans)}件の画像を削除しますか？ (y/N) > ")
    if confirm.lower() != "y":
        print("キャンセルしました")
        return

    deleted = 0
    for f in orphans:
        try:
            f.unlink()
            deleted += 1
        except Exception as e:
            print(f"  ❌ {f.name}: {e}")

    print(f"\n✅ {deleted}件削除完了 ({total_size:.1f} MB 解放)")

if __name__ == "__main__":
    main()
