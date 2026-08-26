import json
import requests
import os
import sys

print("[JWT] Starting token generation...")

# Check if accounts file exists
if not os.path.exists("accounts-BD.json"):
    print("[ERROR] accounts-BD.json not found!")
    sys.exit(1)

with open("accounts-BD.json", "r") as f:
    accounts = json.load(f)

print(f"[JWT] Loaded {len(accounts)} accounts")

tokens = []
success = 0
failed = 0

for acc in accounts:
    uid = str(acc.get("uid", ""))
    password = acc.get("password", "")

    if not uid or not password:
        print(f"[SKIP] Missing uid or password for {uid}")
        continue

    try:
        url = f"https://ff-jwt-gen-api.lovable.app/api/public/token?uid={uid}&password={password}"
        r = requests.get(url, timeout=30)
        data = r.json()

        if data.get("token"):
            tokens.append({
                "uid": uid,
                "token": data["token"],
                "region": data.get("region", "BD"),
                "account_id": data.get("account_id", "")
            })
            success += 1
            print(f"[OK] {uid}")
        else:
            failed += 1
            print(f"[FAIL] {uid} - No token in response: {data}")

    except Exception as e:
        failed += 1
        print(f"[ERROR] {uid}: {e}")

print(f"[JWT] Done: {success} success, {failed} failed")

# Write token file
with open("token_bd.json", "w") as f:
    json.dump(tokens, f, indent=2)

print(f"[JWT] Saved {len(tokens)} tokens to token_bd.json")

# Also print first few tokens for verification
if tokens:
    print("[JWT] Sample token:", tokens[0]["token"][:50] + "...")