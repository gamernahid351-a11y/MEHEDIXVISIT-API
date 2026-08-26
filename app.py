#!/usr/bin/env python3
"""
🔥 Free Fire Visit API — With Nickname Info 🔥
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import aiohttp
import asyncio
import json
import os
import warnings
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import jwt

warnings.filterwarnings("ignore")

app = Flask(__name__)
CORS(app)

# ── Config ────────────────────────────────────────────────────────────
VISITS_TARGET      = 2000
BATCH_TOKENS       = 100000
MAX_FAIL_ROUNDS    = 10
REQUEST_TIMEOUT    = 120

AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV  = b'6oyZDr22E3ychjM%'

# ── Token Cache ──────────────────────────────────────────────────────
_token_cache = {}
CACHE_TTL = 60

def load_tokens(region="BD"):
    filename = f"token_{region.lower()}.json"
    
    if region in _token_cache and (time.time() - _token_cache.get(region, {}).get("time", 0)) < CACHE_TTL:
        return _token_cache[region]["tokens"]
    
    if not os.path.exists(filename):
        print(f"[!] {filename} not found!")
        return []
    
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        
        tokens = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    token = item.get('token')
                    if token:
                        try:
                            decoded = jwt.decode(token, options={"verify_signature": False})
                            if decoded.get('exp', 0) > time.time():
                                tokens.append(token)
                        except:
                            pass
        elif isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    token = value.get('token')
                    if token:
                        try:
                            decoded = jwt.decode(token, options={"verify_signature": False})
                            if decoded.get('exp', 0) > time.time():
                                tokens.append(token)
                        except:
                            pass
        
        _token_cache[region] = {"tokens": tokens, "time": time.time()}
        print(f"[✓] Loaded {len(tokens)} valid tokens from {filename}")
        return tokens
    except Exception as e:
        print(f"[✗] Error loading {filename}: {e}")
        return []

# ── Crypto Functions ──────────────────────────────────────────────────
def encrypt_api(plain_text):
    try:
        plain_text = bytes.fromhex(plain_text)
    except:
        return ""
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(pad(plain_text, AES.block_size)).hex()

def Encrypt_ID(x):
    try:
        x = int(x)
    except:
        return ""
    dec = ['80','81','82','83','84','85','86','87','88','89','8a','8b','8c','8d','8e','8f',
           '90','91','92','93','94','95','96','97','98','99','9a','9b','9c','9d','9e','9f',
           'a0','a1','a2','a3','a4','a5','a6','a7','a8','a9','aa','ab','ac','ad','ae','af',
           'b0','b1','b2','b3','b4','b5','b6','b7','b8','b9','ba','bb','bc','bd','be','bf',
           'c0','c1','c2','c3','c4','c5','c6','c7','c8','c9','ca','cb','cc','cd','ce','cf',
           'd0','d1','d2','d3','d4','d5','d6','d7','d8','d9','da','db','dc','dd','de','df',
           'e0','e1','e2','e3','e4','e5','e6','e7','e8','e9','ea','eb','ec','ed','ee','ef',
           'f0','f1','f2','f3','f4','f5','f6','f7','f8','f9','fa','fb','fc','fd','fe','ff']
    xxx = ['1','01','02','03','04','05','06','07','08','09','0a','0b','0c','0d','0e','0f',
           '10','11','12','13','14','15','16','17','18','19','1a','1b','1c','1d','1e','1f',
           '20','21','22','23','24','25','26','27','28','29','2a','2b','2c','2d','2e','2f',
           '30','31','32','33','34','35','36','37','38','39','3a','3b','3c','3d','3e','3f',
           '40','41','42','43','44','45','46','47','48','49','4a','4b','4c','4d','4e','4f',
           '50','51','52','53','54','55','56','57','58','59','5a','5b','5c','5d','5e','5f',
           '60','61','62','63','64','65','66','67','68','69','6a','6b','6c','6d','6e','6f',
           '70','71','72','73','74','75','76','77','78','79','7a','7b','7c','7d','7e','7f']
    x = x / 128
    if x > 128:
        x = x / 128
        if x > 128:
            x = x / 128
            if x > 128:
                x = x / 128
                strx = int(x)
                y = (x - strx) * 128
                z = (y - int(y)) * 128
                n = (z - int(z)) * 128
                m = (n - int(n)) * 128
                return dec[int(m)] + dec[int(n)] + dec[int(z)] + dec[int(y)] + xxx[int(x)]
    return ""

# ── Parse Player Info (Nickname, Level, etc.) ──────────────────────
def parse_player(raw: bytes):
    try:
        # Import protobuf if available
        from visit_count_pb2 import Info
        info = Info()
        info.ParseFromString(raw)
        return {
            "uid":      info.AccountInfo.UID,
            "nickname": info.AccountInfo.PlayerNickname,
            "region":   info.AccountInfo.PlayerRegion,
            "level":    info.AccountInfo.Levels,
            "likes":    info.AccountInfo.Likes,
        }
    except Exception:
        return None

# ── Visit Functions ──────────────────────────────────────────────────
def _visit_url(region):
    r = region.upper()
    if r == "IND":              return "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    if r in ("BR","US","SAC","NA"): return "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    if r == "VN":               return "https://clientbp.ggwhitehawk.com/GetPlayerPersonalShow"
    return "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"

async def _send_one(session, url, token, data):
    host = url.replace("https://", "").split("/")[0]
    headers = {"ReleaseVersion": "OB54", "X-GA": "v1 1",
                "Authorization": f"Bearer {token}", "Host": host}
    try:
        async with session.post(url, headers=headers, data=data, ssl=False,
                                timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                body = await resp.read()
                return True, body
            return False, None
    except Exception:
        return False, None

async def _run_visits(uid, region, target=VISITS_TARGET):
    url = _visit_url(region)
    enc = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
    data = bytes.fromhex(enc)
    
    tokens = load_tokens(region)
    if not tokens:
        return 0, 0, None
    
    total_ok = 0
    total_sent = 0
    player_info = None
    fail_rounds = 0
    token_count = len(tokens)
    
    connector = aiohttp.TCPConnector(limit=300, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        while total_ok < target:
            remaining = target - total_ok
            batch_size = min(remaining, BATCH_TOKENS)
            
            tasks = [asyncio.create_task(_send_one(session, url, tokens[i % token_count], data))
                     for i in range(batch_size)]
            results = await asyncio.gather(*tasks)
            
            batch_ok = 0
            for ok, body in results:
                if ok:
                    batch_ok += 1
                    if player_info is None and body:
                        player_info = parse_player(body)
            
            total_ok += batch_ok
            total_sent += batch_size
            
            if total_sent % 1000 == 0 or batch_ok == 0:
                print(f"[visit] uid={uid} region={region} total_ok={total_ok}/{target}")
            
            if batch_ok == 0:
                fail_rounds += 1
                if fail_rounds >= MAX_FAIL_ROUNDS:
                    break
                await asyncio.sleep(0.1)
            else:
                fail_rounds = 0
    
    return total_ok, total_sent, player_info

# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({
        "status": "online",
        "api": "Free Fire Visit API",
        "version": "4.0",
        "credit": "MEHEDI X AURA",
        "endpoints": {
            "visit": "GET /visit?uid=<UID>&region=BD"
        }
    })

@app.route("/visit", methods=["GET"])
def visit():
    uid_str = request.args.get("uid", "").strip()
    region = request.args.get("region", "BD").strip().upper()
    
    if region not in ("BD", "IND", "BR", "US", "SAC", "NA", "VN"):
        return jsonify({"error": "Invalid region"}), 400
    
    if not uid_str or not uid_str.isdigit():
        return jsonify({"error": "Valid uid required"}), 400
    
    uid_int = int(uid_str)
    tokens = load_tokens(region)
    if not tokens:
        return jsonify({"error": f"No valid tokens found in token_{region.lower()}.json"}), 500
    
    print(f"[visit] ▶ uid={uid_int} region={region} tokens={len(tokens)}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        total_ok, total_sent, player_info = loop.run_until_complete(
            asyncio.wait_for(_run_visits(uid_int, region, VISITS_TARGET), timeout=REQUEST_TIMEOUT)
        )
    except asyncio.TimeoutError:
        return jsonify({"error": "Timeout"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        loop.close()
    
    result = {
        "uid": uid_int,
        "region": region,
        "visits_sent": total_sent,
        "visits_success": total_ok,
        "visits_failed": total_sent - total_ok,
        "status": "success" if total_ok >= VISITS_TARGET else "partial",
        "credit": "MEHEDI X AURA"
    }
    
    # Add player info if available
    if player_info:
        result["nickname"] = player_info.get("nickname", "Unknown")
        result["level"] = player_info.get("level", 0)
        result["likes"] = player_info.get("likes", 0)
    
    return jsonify(result), 200 if total_ok >= VISITS_TARGET else 206

# ── Token Status ──────────────────────────────────────────────────────
@app.route("/token-status", methods=["GET"])
def token_status():
    region = request.args.get("region", "BD").strip().upper()
    tokens = load_tokens(region)
    return jsonify({
        "region": region,
        "total_tokens": len(tokens),
        "file": f"token_{region.lower()}.json"
    })

# ── Vercel Handler ──────────────────────────────────────────────────
app_handler = app

# ── Start ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    tokens = load_tokens("BD")
    print(f"[✓] Loaded {len(tokens)} valid JWT tokens")
    print(f"🚀 Server running on http://0.0.0.0:{port}")
    print(f"📌 Visit: http://localhost:{port}/visit?uid=YOUR_UID&region=BD")
    app.run(host="0.0.0.0", port=port, debug=False)
