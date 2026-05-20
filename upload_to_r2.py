import boto3
import json
import time
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

R2_ENDPOINT    = "https://03a918d6e412d0f3b6933b92cfb1d82e.r2.cloudflarestorage.com"
R2_BUCKET      = "pandora-images"
R2_PUBLIC_BASE = "https://pub-9fd7380e75884fad932a9785f182c39e.r2.dev"
ACCESS_KEY     = "e6071157ffb3c35505499b4dad59e6d4"
SECRET_KEY     = "4488a8ea3f08edfd3e2770bea132db1eb59e9d777e11dd82a863cce4570561e4"

IMAGES_DIR    = Path("C:/Users/soram/Desktop/pandora/images")
PRODUCTS_JSON = Path("C:/Users/soram/Desktop/pandora/products.json")
WORKERS       = 10

s3 = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name="auto",
)

def get_uploaded_keys():
    keys = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=R2_BUCKET):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys

def upload_file(fpath, already_uploaded):
    fname = fpath.name
    if fname in already_uploaded:
        return "skip", fname
    try:
        ct = "image/jpeg"
        if fname.endswith(".png"):
            ct = "image/png"
        elif fname.endswith(".webp"):
            ct = "image/webp"
        s3.upload_file(str(fpath), R2_BUCKET, fname, ExtraArgs={"ContentType": ct})
        return "ok", fname
    except Exception as e:
        return "err", f"{fname}: {e}"

def main():
    files = list(IMAGES_DIR.iterdir())
    print(f"ローカル画像: {len(files)}枚")

    print("R2に既存のファイルを確認中...")
    already_uploaded = get_uploaded_keys()
    print(f"R2にアップロード済み: {len(already_uploaded)}枚")

    to_upload = [f for f in files if f.name not in already_uploaded]
    print(f"アップロード対象: {len(to_upload)}枚\n")

    if not to_upload:
        print("全てアップロード済みです。products.jsonを更新します。")
    else:
        ok = skip = err = 0
        start = time.time()
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(upload_file, f, already_uploaded): f for f in to_upload}
            for i, future in enumerate(as_completed(futures), 1):
                status, msg = future.result()
                if status == "ok":
                    ok += 1
                elif status == "skip":
                    skip += 1
                else:
                    err += 1
                    print(f"ERROR: {msg}")
                if i % 100 == 0 or i == len(to_upload):
                    elapsed = time.time() - start
                    rate = ok / elapsed if elapsed > 0 else 0
                    print(f"  {i}/{len(to_upload)} | OK:{ok} SKIP:{skip} ERR:{err} | {rate:.1f}枚/秒")

        print(f"\nアップロード完了: OK={ok} SKIP={skip} ERR={err}")

    # products.json の画像パスを R2 URL に更新
    print("\nproducts.json を更新中...")
    data = json.loads(PRODUCTS_JSON.read_text("utf-8"))
    updated = 0
    for p in data["products"]:
        img = p.get("image", "")
        if img and img.startswith("images/"):
            fname = Path(img).name
            p["image"] = f"{R2_PUBLIC_BASE}/{fname}"
            updated += 1
    data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    PRODUCTS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    print(f"products.json 更新完了: {updated}件のパスをR2 URLに変換")

if __name__ == "__main__":
    main()
