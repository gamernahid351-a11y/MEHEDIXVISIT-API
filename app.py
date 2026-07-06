#!/usr/bin/env python3
"""
Free Fire Visit API — BD / IND Server
Sends 1000 visits to a Free Fire player profile.
Usage: GET /visit?uid=<UID>&region=BD
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import aiohttp
import asyncio
import json
import os
import sys
import glob
import warnings
import threading
import time
import tempfile
import requests as req_lib
from concurrent.futures import ThreadPoolExecutor, as_completed
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from byte import encrypt_api, Encrypt_ID
from visit_count_pb2 import Info
from protobuf import my_pb2, output_pb2

app = Flask(__name__)
CORS(app)

# ── Security ──────────────────────────────────────────────────────────
import secrets as _secrets

_ACCOUNTS_SECURITY_CODE = os.environ.get("ACCOUNTS_SECURITY_CODE", "mehedixaura")

_ADMIN_KEY = os.environ.get("ADMIN_KEY") or _secrets.token_hex(16)
if not os.environ.get("ADMIN_KEY"):
    print(f"[admin] No ADMIN_KEY set — generated random key: {_ADMIN_KEY}")

def _check_admin():
    key = request.headers.get("X-Admin-Key") or ""
    if key != _ADMIN_KEY:
        return jsonify({"error": "Unauthorized. Pass X-Admin-Key header."}), 401
    return None

def _check_security():
    code = request.headers.get("X-Security-Code") or ""
    if code != _ACCOUNTS_SECURITY_CODE:
        return jsonify({"error": "Invalid security code. Pass X-Security-Code header."}), 401
    return None

# ── Config ────────────────────────────────────────────────────────────
VISITS_TARGET      = 5000
BATCH_TOKENS       = 69
MAX_FAIL_ROUNDS    = 10
REQUEST_TIMEOUT    = 120
AUTO_REGEN_HOURS   = 5

AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV  = b'6oyZDr22E3ychjM%'

_token_cache: dict = {}
_token_lock   = threading.RLock()
_gen_executor = ThreadPoolExecutor(max_workers=80)

# ── Helpers ───────────────────────────────────────────────────────────

def _token_file(region: str) -> str:
    r = region.upper()
    if r == "IND":              return "token_ind.json"
    if r in {"BR","US","SAC","NA"}: return "token_br.json"
    if r == "VN":               return "token_vn.json"
    return "token_bd.json"

def _base_dir():
    return os.path.dirname(os.path.abspath(__file__))

def _load_tokens(region: str) -> list:
    path = os.path.join(_base_dir(), _token_file(region))
    if not os.path.exists(path):
        return []
    try:
        with _token_lock:
            with open(path) as f:
                data = json.load(f)
        return [d["token"] for d in data if d.get("token") not in ("", "N/A", None)]
    except Exception as e:
        app.logger.error(f"[token] Load error: {e}")
        return []

def _get_token_batch(region: str) -> list:
    r = region.upper()

    with _token_lock:
        if r not in _token_cache:
            _token_cache[r] = {
                "tokens": _load_tokens(r),
                "idx": 0
            }

        tokens = _token_cache[r]["tokens"]

        if not tokens:
            return []

        return tokens.copy()

def _visit_url(region: str) -> str:
    r = region.upper()
    if r == "IND":              return "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    if r in {"BR","US","SAC","NA"}: return "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    if r == "VN":               return "https://clientbp.ggwhitehawk.com/GetPlayerPersonalShow"
    return "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"

def _parse_player(raw: bytes):
    try:
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

# ── Token generation from accounts ───────────────────────────────────

def _aes_encrypt(data: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(pad(data, AES.block_size))

def _parse_login_response(content: bytes) -> dict:
    try:
        msg = output_pb2.Garena_420()
        msg.ParseFromString(content)
        result = {}
        for line in str(msg).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                result[k.strip()] = v.strip().strip('"')
        return result
    except Exception as e:
        return {"error": str(e)}

def _generate_jwt(uid, password) -> dict:
    try:
        r = req_lib.post(
            "https://100067.connect.garena.com/oauth/guest/token/grant",
            headers={"User-Agent": "GarenaMSDK/4.0.19P9(SM-M526B ;Android 13;pt;BR;)",
                     "Connection": "Keep-Alive", "Accept-Encoding": "gzip"},
            data={"uid": uid, "password": password, "response_type": "token",
                  "client_type": "2",
                  "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
                  "client_id": "100067"},
            timeout=10
        )
        j = r.json()
        access_token = j.get("access_token") or j.get("token") or j.get("session_key")
        open_id = j.get("open_id", "")
        if not access_token:
            return {"success": False, "error": "No access_token", "uid": uid}
    except Exception as e:
        return {"success": False, "error": str(e), "uid": uid}

    try:
        gd = my_pb2.GameData()
        gd.timestamp = "2024-12-05 18:15:32"
        gd.game_name = "free fire"
        gd.game_version = 1
        gd.version_code = "1.108.3"
        gd.os_info = "Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)"
        gd.device_type = "Handheld"
        gd.network_provider = "Verizon Wireless"
        gd.connection_type = "WIFI"
        gd.screen_width = 1280
        gd.screen_height = 960
        gd.dpi = "240"
        gd.cpu_info = "ARMv7 VFPv3 NEON VMH | 2400 | 4"
        gd.total_ram = 5951
        gd.gpu_name = "Adreno (TM) 640"
        gd.gpu_version = "OpenGL ES 3.0"
        gd.user_id = "Google|74b585a9-0268-4ad3-8f36-ef41d2e53610"
        gd.ip_address = "172.190.111.97"
        gd.language = "en"
        gd.open_id = open_id
        gd.access_token = access_token
        gd.platform_type = 4
        gd.device_form_factor = "Handheld"
        gd.device_model = "Asus ASUS_I005DA"
        gd.field_60 = 32968; gd.field_61 = 29815; gd.field_62 = 2479; gd.field_63 = 914
        gd.field_64 = 31213; gd.field_65 = 32968; gd.field_66 = 31213; gd.field_67 = 32968
        gd.field_70 = 4; gd.field_73 = 2
        gd.library_path = "/data/app/com.dts.freefireth-QPvBnTUhYWE-7DMZSOGdmA==/lib/arm"
        gd.field_76 = 1
        gd.apk_info = "5b892aaabd688e571f688053118a162b|/data/app/com.dts.freefireth-QPvBnTUhYWE-7DMZSOGdmA==/base.apk"
        gd.field_78 = 6; gd.field_79 = 1
        gd.os_architecture = "32"
        gd.build_number = "2019117877"
        gd.field_85 = 1
        gd.graphics_backend = "OpenGLES2"
        gd.max_texture_units = 16383
        gd.rendering_api = 4
        gd.encoded_field_89 = "\x17T\x11\x17\x02\x08\x0eUMQ\x08EZ\x03@ZK;Z\x02\x0eV\ri[QVi\x03\ro\x07e"
        gd.field_92 = 9204
        gd.marketplace = "3rd_party"
        gd.encryption_key = "KqsHT2B4It60T/65PGR5PXwFxQkVjGNi+IMCK3CFBCBfrNpSUA1dZnjaT3HcYchlIFFL1ZJOg0cnulKCPGD3C3h1eFQ="
        gd.total_storage = 111107
        gd.field_97 = 1; gd.field_98 = 1
        gd.field_99 = "4"; gd.field_100 = "4"
        encrypted = _aes_encrypt(gd.SerializeToString())
        resp = req_lib.post(
            "https://loginbp.ggpolarbear.com/MajorLogin",
            data=encrypted,
            headers={"User-Agent": "GarenaMSDK/4.0.19P9(Android 13)", "Connection": "Keep-Alive",
                     "Accept-Encoding": "gzip", "Content-Type": "application/x-www-form-urlencoded",
                     "X-Unity-Version": "2018.4.11f1", "X-GA": "v1 1", "ReleaseVersion": "OB54"},
            verify=False, timeout=15
        )
        if resp.status_code == 200:
            parsed = _parse_login_response(resp.content)
            jwt = parsed.get("token", "")
            region = parsed.get("region", "BD")
            api = parsed.get("api", "")
            if jwt and jwt not in ("", "N/A", "null"):
                return {"success": True, "uid": str(uid), "token": jwt, "region": region, "api": api}
            return {"success": False, "error": "No JWT in response", "uid": uid}
        return {"success": False, "error": f"HTTP {resp.status_code}", "uid": uid}
    except Exception as e:
        return {"success": False, "error": str(e), "uid": uid}

def _load_accounts(region: str = None) -> list:
    accounts = []
    pattern = os.path.join(_base_dir(), "accounts-*.json")
    for fpath in glob.glob(pattern):
        try:
            with open(fpath) as f:
                data = json.load(f)
            if isinstance(data, list):
                for acc in data:
                    if "uid" in acc and "password" in acc:
                        acc_region = str(acc.get("region", "BD")).upper()
                        if region is None or acc_region == region.upper():
                            accounts.append({
                                "uid": str(acc["uid"]),
                                "password": str(acc["password"]),
                                "region": acc_region
                            })
        except Exception as e:
            app.logger.error(f"[accounts] Error loading {fpath}: {e}")
    return accounts

def _do_generate_tokens(region: str = None):
    accounts = _load_accounts(region)
    if not accounts:
        return {"success": False, "error": "No accounts found"}
    total = len(accounts)
    print(f"[gen] Generating tokens for {total} accounts (region={region or 'ALL'})")
    all_tokens: dict = {}
    ok = 0; fail = 0
    futures = {_gen_executor.submit(_generate_jwt, acc["uid"], acc["password"]): acc for acc in accounts}
    for i, future in enumerate(as_completed(futures), 1):
        acc = futures[future]
        try:
            result = future.result()
            if result.get("success"):
                r = result["region"]
                all_tokens.setdefault(r, []).append({
                    "uid": result["uid"], "token": result["token"],
                    "region": r, "api": result.get("api", "")
                })
                ok += 1
                print(f"[gen] [{i}/{total}] ✅ {result['uid']} ({r})")
            else:
                fail += 1
                if i % 20 == 0:
                    print(f"[gen] [{i}/{total}] ❌ {acc['uid']}: {result.get('error')}")
        except Exception as e:
            fail += 1
    # Atomic write (tempfile + os.replace) under lock
    for r, tokens in all_tokens.items():
        path    = os.path.join(_base_dir(), _token_file(r))
        dirpath = os.path.dirname(path)
        with _token_lock:
            try:
                fd, tmp = tempfile.mkstemp(dir=dirpath, suffix=".tmp")
                with os.fdopen(fd, "w") as f:
                    json.dump(tokens, f, indent=2)
                os.replace(tmp, path)
            except Exception as e:
                print(f"[gen] ⚠️  Failed to write {path}: {e}")
                continue
            _token_cache[r] = {"tokens": [t["token"] for t in tokens], "idx": 0}
        print(f"[gen] 💾 Saved {len(tokens)} tokens → {_token_file(r)}")
    return {
        "success": True, "generated": ok, "failed": fail,
        "regions": {r: len(t) for r, t in all_tokens.items()}
    }

# ── Auto token regeneration every 5 hours ────────────────────────────

def _auto_regen_loop():
    interval = AUTO_REGEN_HOURS * 3600
    while True:
        time.sleep(interval)
        print(f"[auto-regen] ⏰ {AUTO_REGEN_HOURS}h elapsed — regenerating all tokens...")
        try:
            result = _do_generate_tokens(region=None)
            print(f"[auto-regen] ✅ Done: {result}")
        except Exception as e:
            print(f"[auto-regen] ❌ Error: {e}")

_regen_thread = threading.Thread(target=_auto_regen_loop, daemon=True, name="auto-regen")
_regen_thread.start()
print(f"[auto-regen] 🔄 Started — will regenerate JWT every {AUTO_REGEN_HOURS} hours")

# ── Async visit logic ─────────────────────────────────────────────────

async def _send_one(session, url, token, data):
    host = url.replace("https://", "").split("/")[0]
    headers = {"ReleaseVersion": "OB54", "X-GA": "v1 1",
                "Authorization": f"Bearer {token}", "Host": host}
    try:
        async with session.post(url, headers=headers, data=data, ssl=False,
                                timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                body = await resp.read()
                return True, body
            return False, None
    except Exception:
        return False, None

async def _run_visits(uid, region, target=VISITS_TARGET):
    url  = _visit_url(region)
    enc  = encrypt_api("08" + Encrypt_ID(str(uid)) + "1801")
    data = bytes.fromhex(enc)
    total_ok = 0; total_sent = 0; player_info = None; fail_rounds = 0

    connector = aiohttp.TCPConnector(limit=0, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        while total_ok < target:
            tokens = _get_token_batch(region)
            if not tokens: break
            remaining  = target - total_ok
            batch_size = min(remaining, len(tokens))
            tasks   = [asyncio.create_task(_send_one(session, url, tokens[i % len(tokens)], data))
                       for i in range(batch_size)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_ok = 0
            for r in results:
                if isinstance(r, tuple):
                    ok, body = r
                    if ok:
                        batch_ok += 1
                        if player_info is None and body:
                            player_info = _parse_player(body)
            total_ok += batch_ok; total_sent += batch_size
            print(f"[visit] uid={uid} region={region} batch_ok={batch_ok}/{batch_size} total={total_ok}/{target}")
            if batch_ok == 0:
                fail_rounds += 1
                if fail_rounds >= MAX_FAIL_ROUNDS: break
                await asyncio.sleep(0.2)
            else:
                fail_rounds = 0
    return total_ok, total_sent, player_info

# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({
        "status": "online", "api": "Free Fire Visit API", "version": "2.0",
        "auto_regen_hours": AUTO_REGEN_HOURS,
        "endpoints": {
            "visit":           "GET  /visit?uid=<UID>&region=BD|IND",
            "token_status":    "GET  /token-status/<REGION>",
            "reload":          "POST /reload-tokens  [X-Admin-Key]",
            "gen_tokens":      "POST /generate-tokens?region=BD|IND  [X-Admin-Key]",
            "accounts_list":   "GET  /accounts?region=BD|IND  [X-Security-Code]",
            "accounts_upload": "POST /accounts/upload  [X-Security-Code]  body: JSON array",
            "accounts_delete": "POST /accounts/delete  [X-Security-Code]  body: {region}",
        },
        "credit": "MEHEDI X AURA"
    })

@app.route("/visit", methods=["GET"])
def visit():
    uid_str = request.args.get("uid", "").strip()
    region  = request.args.get("region", "BD").strip().upper()
    if region not in ("BD", "IND", "BR", "US", "SAC", "NA", "VN"):
        return jsonify({"error": "Invalid region. Use: BD, IND, BR, US, NA, VN"}), 400
    if not uid_str:
        return jsonify({"error": "Missing uid. Example: /visit?uid=8568636511&region=BD"}), 400
    try:
        uid_int = int(uid_str)
    except ValueError:
        return jsonify({"error": "uid must be a number"}), 400
    tokens = _load_tokens(region)
    if not tokens:
        return jsonify({"error": f"No tokens for region {region}. Try POST /generate-tokens?region={region}"}), 500
    print(f"[visit] ▶ uid={uid_int} region={region} tokens_available={len(tokens)}")
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

    base = {
        "uid":            player_info.get("uid") if player_info else uid_int,
        "nickname":       player_info.get("nickname", "") if player_info else "",
        "region":         player_info.get("region", region) if player_info else region,
        "level":          player_info.get("level", 0) if player_info else 0,
        "likes":          player_info.get("likes", 0) if player_info else 0,
        "visits_sent":    total_sent,
        "visits_success": total_ok,
        "visits_failed":  total_sent - total_ok,
        "tokens_used":    min(len(tokens), BATCH_TOKENS),
        "credit":         "MEHEDI X AURA",
    }
    if total_ok >= VISITS_TARGET:
        base["status"] = "success"
        return jsonify(base), 200
    else:
        base["status"] = "partial"
        base["note"] = f"Only {total_ok}/{VISITS_TARGET} visits succeeded. Tokens may be expired."
        return jsonify(base), 206

@app.route("/token-status/<string:region>", methods=["GET"])
def token_status(region):
    r      = region.upper()
    tokens = _load_tokens(r)
    state  = _token_cache.get(r, {})
    return jsonify({
        "region": r, "total_tokens": len(tokens),
        "current_index": state.get("idx", 0),
        "file": _token_file(r),
        "status": "ok" if tokens else "empty"
    })

@app.route("/reload-tokens", methods=["POST"])
def reload_tokens():
    err = _check_admin()
    if err: return err
    with _token_lock:
        _token_cache.clear()
    return jsonify({"status": "cache cleared — tokens reload on next request"})

@app.route("/generate-tokens", methods=["POST"])
def generate_tokens():
    err = _check_admin()
    if err: return err
    region = request.args.get("region", None)
    if region:
        region = region.upper()
    try:
        result = _do_generate_tokens(region)
        return jsonify(result), 200 if result.get("success") else 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Accounts management ───────────────────────────────────────────────

@app.route("/accounts", methods=["GET"])
def accounts_list():
    err = _check_security()
    if err: return err
    region = request.args.get("region", None)
    if region:
        region = region.upper()
    files = []
    for fpath in sorted(glob.glob(os.path.join(_base_dir(), "accounts-*.json"))):
        fname = os.path.basename(fpath)
        try:
            with open(fpath) as f:
                data = json.load(f)
            count = len(data) if isinstance(data, list) else 0
            regions_in = list({str(a.get("region","?")).upper() for a in data if isinstance(a, dict)})
        except Exception:
            count = 0; regions_in = []
        if region is None or region in regions_in:
            files.append({"file": fname, "count": count, "regions": regions_in})
    total_accounts = _load_accounts(region)
    return jsonify({
        "files": files,
        "total_accounts": len(total_accounts),
        "filter_region": region or "ALL"
    })

@app.route("/accounts/upload", methods=["POST"])
def accounts_upload():
    err = _check_security()
    if err: return err
    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({"error": "Body must be a JSON array [{uid, password, region}, ...]"}), 400
    valid = []
    for acc in data:
        if not isinstance(acc, dict): continue
        uid = str(acc.get("uid","")).strip()
        pw  = str(acc.get("password","")).strip()
        reg = str(acc.get("region","BD")).strip().upper()
        if uid and pw:
            valid.append({"uid": uid, "password": pw, "region": reg})
    if not valid:
        return jsonify({"error": "No valid accounts found in body"}), 400
    by_region: dict = {}
    for acc in valid:
        by_region.setdefault(acc["region"], []).append(acc)
    merge = request.args.get("merge", "false").lower() == "true"
    saved = {}
    for reg, accs in by_region.items():
        fpath = os.path.join(_base_dir(), f"accounts-{reg}.json")
        if merge and os.path.exists(fpath):
            try:
                with open(fpath) as f:
                    existing = json.load(f)
                existing_uids = {str(a.get("uid")) for a in existing if isinstance(a, dict)}
                new_only = [a for a in accs if str(a["uid"]) not in existing_uids]
                merged = existing + new_only
                with open(fpath, "w") as f:
                    json.dump(merged, f, indent=2)
                saved[reg] = {"action": "merged", "added": len(new_only), "total": len(merged)}
            except Exception as e:
                saved[reg] = {"action": "error", "error": str(e)}
        else:
            with open(fpath, "w") as f:
                json.dump(accs, f, indent=2)
            saved[reg] = {"action": "replaced", "total": len(accs)}
        with _token_lock:
            _token_cache.pop(reg, None)
        print(f"[accounts] 📁 Saved {fpath} — {saved[reg]}")
    return jsonify({
        "success": True,
        "message": "Accounts saved. Use POST /generate-tokens to generate fresh JWT tokens.",
        "saved": saved
    })

@app.route("/accounts/delete", methods=["POST"])
def accounts_delete():
    err = _check_security()
    if err: return err
    body   = request.get_json(silent=True) or {}
    region = str(body.get("region", "")).strip().upper()
    if not region:
        return jsonify({"error": 'Provide region in body: {"region": "BD"} or {"region": "ALL"}'}), 400
    if region == "ALL":
        targets = glob.glob(os.path.join(_base_dir(), "accounts-*.json"))
    else:
        targets = [os.path.join(_base_dir(), f"accounts-{region}.json")]
    deleted = []
    for fpath in targets:
        if os.path.exists(fpath):
            os.remove(fpath)
            reg = os.path.basename(fpath).replace("accounts-","").replace(".json","")
            with _token_lock:
                _token_cache.pop(reg, None)
            deleted.append(os.path.basename(fpath))
            print(f"[accounts] 🗑️  Deleted {fpath}")
    if not deleted:
        return jsonify({"error": f"No accounts file found for region={region}"}), 404
    return jsonify({
        "success": True,
        "deleted_files": deleted,
        "message": "Accounts deleted. Token cache cleared."
    })
if __name__ == "__main__":
    print("[startup] Generating BD tokens...")
    _do_generate_tokens("BD")
    print("[startup] BD token generation completed.")

    port = int(os.environ.get("PORT", 3000))
    print(f"🚀 Visit API on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)