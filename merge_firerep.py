#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""enrichment 後に backup から firerep データを products.json に再マージする。"""
import json
from pathlib import Path
from collections import Counter

# enrichment が書き込んだ最新の products.json
data = json.loads(Path("products.json").read_text("utf-8"))
existing_yupoo = {p["yupoo"] for p in data["products"] if p.get("yupoo")}

# firerep 追加前の backup から firerep 商品だけ取り出す
backup = json.loads(Path("products_backup_with_firerep.json").read_text("utf-8"))
firerep_products = [p for p in backup["products"] if p.get("seller") == "firerep"]

print(f"backup 内の firerep 商品: {len(firerep_products)} 件")
print("ブランド内訳:", dict(Counter(p["brand"] for p in firerep_products)))

added = 0
for p in firerep_products:
    if p.get("yupoo") not in existing_yupoo:
        data["products"].append(p)
        existing_yupoo.add(p["yupoo"])
        added += 1

print(f"追加: {added} 件 / 重複スキップ: {len(firerep_products) - added} 件")

if added > 0:
    Path("products.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8"
    )
    print("products.json 更新完了")
    total = len(data["products"])
    print(f"Total products: {total}")
else:
    print("全件既に存在 (マージ不要)")
