#!/usr/bin/env python3
"""
🔥 FREE FIRE VISIT API - VERCEL FIXED 🔥
Owner: @bigbullghost999
"""

import os
import sys
import json
import time
import asyncio
import aiohttp
import warnings
from flask import Flask, jsonify, request
from flask_cors import CORS
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import jwt

warnings.filterwarnings("ignore")

# ============================================================
#  CONFIG
# ============================================================
VISITS_TARGET = 10000
MAX_FAIL_ROUNDS = 3
REQUEST_TIMEOUT = 240
AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'

# ============================================================
#  FLASK APP
# ============================================================
app = Flask(__name__)
CORS(app)

# ============================================================
#  CRYPTO FUNCTIONS
# ============================================================
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

# ============================================================
#  TOKEN LOADER - token_bd.json
# ============================================================
def load_tokens(region="BD"):
    filename = f"token_{region.lower()}.json"
    
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
                            exp = decoded.get('exp', 0)
                            if exp > time.time():
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
                            exp = decoded.get('exp', 0)
                            if exp > time.time():
                                tokens.append(token)
                        except:
                            pass
        
        print(f"[✓] Loaded {len(tokens)} valid tokens from {filename}")
        return tokens
    except Exception as e:
        print(f"[✗] Error loading {filename}: {e}")
        return []

# ============================================================
#  VISIT FUNCTIONS
# ============================================================
async def _send_one(session, url, token, data):
    host = url.replace("https://", "").split("/")[0]
    headers = {
        "ReleaseVersion": "OB54",
        "X-GA": "v1 1",
        "Authorization": f"Bearer {token}",
        "Host": host
    }
    try:
        async with session.post(url, headers=headers, data=data, ssl=False,
                                timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                body = await resp.read()
                return True, body
            return False, None
    except Exception:
        return False, None

def _visit_url(region):
    r = region.upper()
    if r == "IND":
        return "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    if r in ("BR", "US", "SAC", "NA"):
        return "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    if r == "VN":
        return "https://clientbp.ggwhitehawk.com/GetPlayerPersonalShow"
    return "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"

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
    
    connector = aiohttp.TCPConnector(limit=50, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        while total_ok < target:
            remaining = target - total_ok
            batch_size = min(remaining, len(tokens))
            
            import random
            batch_tokens = random.sample(tokens, min(batch_size, len(tokens)))
            
            tasks = []
            for token in batch_tokens:
                tasks.append(asyncio.create_task(_send_one(session, url, token, data)))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            batch_ok = 0
            for r in results:
                if isinstance(r, tuple):
                    ok, body = r
                    if ok:
                        batch_ok += 1
                        if player_info is None and body:
                            try:
                                player_info = {"uid": uid}
                            except:
                                pass
            
            total_ok += batch_ok
            total_sent += len(batch_tokens)
            
            print(f"[visit] uid={uid} region={region} batch_ok={batch_ok}/{len(batch_tokens)} total={total_ok}/{target}")
            
            if batch_ok == 0:
                fail_rounds += 1
                if fail_rounds >= MAX_FAIL_ROUNDS:
                    print(f"[visit] ❌ All tokens failed after {MAX_FAIL_ROUNDS} rounds!")
                    break
                await asyncio.sleep(1)
            else:
                fail_rounds = 0
    
    return total_ok, total_sent, player_info

# ============================================================
#  ROUTES
# ============================================================
@app.route("/")
def index():
    return jsonify({
        "status": "online",
        "api": "Free Fire Visit API",
        "version": "3.0",
        "credit": "MEHEDI X AURA",
        "token_file": "token_bd.json",
        "endpoints": {
            "visit": "GET /visit?uid=<UID>&region=BD"
        }
    })

@app.route("/visit", methods=["GET"])
def visit():
    uid_str = request.args.get("uid", "").strip()
    region = request.args.get("region", "BD").strip().upper()
    
    if region not in ("BD", "IND", "BR", "US", "SAC", "NA", "VN"):
        return jsonify({"error": "Invalid region. Use: BD, IND, BR, US, NA, VN"}), 400
    
    if not uid_str:
        return jsonify({"error": "Missing uid. Example: /visit?uid=8568636511&region=BD"}), 400
    
    try:
        uid_int = int(uid_str)
    except ValueError:
        return jsonify({"error": "uid must be a number"}), 400
    
    tokens = load_tokens(region)
    if not tokens:
        return jsonify({"error": f"No valid tokens found in token_{region.lower()}.json"}), 500
    
    print(f"[visit] ▶ uid={uid_int} region={region} valid_tokens={len(tokens)}")
    
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        total_ok, total_sent, player_info = loop.run_until_complete(
            asyncio.wait_for(_run_visits(uid_int, region, VISITS_TARGET), timeout=REQUEST_TIMEOUT)
        )
    except asyncio.TimeoutError:
        return jsonify({"error": f"Timed out after {REQUEST_TIMEOUT}s"}), 504
    except Exception as e:
        return jsonify({"error": f"Visit failed: {str(e)}"}), 500
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
    
    return jsonify(result), 200 if total_ok >= VISITS_TARGET else 206

# ============================================================
#  TOKEN STATUS
# ============================================================
@app.route("/token-status", methods=["GET"])
def token_status():
    region = request.args.get("region", "BD").strip().upper()
    tokens = load_tokens(region)
    return jsonify({
        "region": region,
        "total_tokens": len(tokens),
        "file": f"token_{region.lower()}.json"
    })

# ============================================================
#  VERCEL COMPATIBLE HANDLER
# ============================================================
# Vercel uses this as entry point
app_handler = app

# ============================================================
#  START
# ============================================================
if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║     ██╗   ██╗██╗  ████████╗██████╗  █████╗              ║
║     ██║   ██║██║  ╚══██╔══╝██╔══██╗██╔══██╗             ║
║     ██║   ██║██║     ██║   ██████╔╝███████║             ║
║     ██║   ██║██║     ██║   ██╔══██╗██╔══██║             ║
║     ╚██████╔╝███████╗██║   ██║  ██║██║  ██║             ║
║      ╚═════╝ ╚══════╝╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝             ║
╚═══════════════════════════════════════════════════════════╝
    """)
    print("🔥 VISIT API - VERCEL FIXED")
    print("📩 OWNER: @bigbullghost999\n")
    
    port = int(os.environ.get("PORT", 3000))
    
    tokens = load_tokens("BD")
    print(f"[✓] Loaded {len(tokens)} valid JWT tokens")
    
    print(f"🚀 Server running on http://0.0.0.0:{port}")
    print(f"📌 Visit: http://localhost:{port}/visit?uid=YOUR_UID&region=BD")
    
    app.run(host="0.0.0.0", port=port, debug=False)