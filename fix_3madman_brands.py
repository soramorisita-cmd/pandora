#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3madman の brand/type 補完 (カスタム略称対応)。"""
import json, re
from collections import Counter
from pathlib import Path

from add_seller import detect_brand_from_text, classify

# 3madman 専用の略称マッピング（標準辞書の前に適用）
CUSTOM_SLANG = [
    ("cdg play", "Comme des Garçons"),
    ("comme des garcons", "Comme des Garçons"),
    ("cdg bape", "Comme des Garçons"),
    (" cdg ", "Comme des Garçons"),
    ("akimbo", "Akimbo"),
    ("akim ", "Akimbo"),
    ("stussy", "Stussy"),
    (" stu ", "Stussy"),
    ("dime ", "Dime"),
    (" dime ", "Dime"),
    ("d*me ", "Dime"),
    ("protect ", "Protect"),
    ("pro*ect", "Protect"),
    ("prote*ct", "Protect"),
    ("gallery dept", "Gallery Dept"),
    ("gallery ", "Gallery Dept"),
    ("carhartt", "Carhartt"),
    ("carha*rt", "Carhartt"),
    ("acne ", "Acne Studios"),
    ("ac*e ", "Acne Studios"),
    ("palace", "Palace"),
    (" sup ", "Supreme"),
    ("blcg", "Balenciaga"),
    (" nk ", "NIKE"),
    ("n*k ", "NIKE"),
    ("travis scott", "Travis Scott"),
    ("l*v ", "Louis Vuitton"),
    (" ate ", "Ate"),
    ("a*te ", "Ate"),
    ("ate ", "Ate"),
]

def detect_custom(title: str) -> str | None:
    tl = " " + title.lower() + " "
    for slang, brand in CUSTOM_SLANG:
        if slang in tl:
            return brand
    return detect_brand_from_text(title)

data = json.loads(Path("products.json").read_text("utf-8"))
targets = [p for p in data["products"] if p.get("seller") == "3madman"]
print(f"3madman 商品: {len(targets)} 件")

fixed_brand = 0
fixed_type = 0
for p in targets:
    title = p.get("title", "")
    if not title:
        continue
    new_brand = detect_custom(title)
    if new_brand and p.get("brand") in ("Other", "", None):
        p["brand"] = new_brand
        fixed_brand += 1
    new_type = classify(title)
    if new_type != "Other" and p.get("type") == "Other":
        p["type"] = new_type
        fixed_type += 1

print(f"ブランド修正: {fixed_brand}/{len(targets)} 件")
print(f"タイプ修正: {fixed_type}/{len(targets)} 件")

Path("products.json").write_text(
    json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8"
)

prods = [p for p in data["products"] if p.get("seller") == "3madman"]
print("\nブランド分布:")
for b, n in Counter(p["brand"] for p in prods).most_common(20):
    print(f"  {b}: {n}")
print("\nタイプ分布:")
for t, n in Counter(p["type"] for p in prods).most_common():
    print(f"  {t}: {n}")
