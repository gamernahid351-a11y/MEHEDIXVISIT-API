import json
import requests

with open("accounts-BD.json", "r") as f:
    accounts = json.load(f)

tokens = []

for acc in accounts:
    uid = str(acc["uid"])
    password = acc["password"]

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

            print(f"OK {uid}")
        else:
            print(f"FAIL {uid}")

    except Exception as e:
        print(f"ERROR {uid}: {e}")

with open("token_bd.json", "w") as f:
    json.dump(tokens, f, indent=2)