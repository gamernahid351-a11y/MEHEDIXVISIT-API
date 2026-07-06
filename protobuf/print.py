
# Fixed code based on actual protobuf definition
# Access fields directly from protobuf message object instead of parsing string

fixed_final_code = '''import sys
sys.path.append("/")

from flask import Flask, jsonify, request, make_response
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import binascii
from protobuf import my_pb2, output_pb2

import os
import warnings
from urllib3.exceptions import InsecureRequestWarning
import base64
import json

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'

app = Flask(__name__)

def get_token(password, uid):
    url = "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant"

    headers = {
        "User-Agent": "GarenaMSDK/4.0.19P4(G011A ;Android 9;en;US;)",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "uid": uid,
        "password": password,
        "response_type": "token",
        "client_type": "2",
        "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
        "client_id": "100067"
    }

    r = requests.post(url, headers=headers, data=data)

    try:
        j = r.json()
    except:
        return {
            "error": "OAuth non JSON",
            "raw": r.text
        }

    token = (
        j.get("access_token")
        or j.get("token")
        or j.get("session_key")
        or j.get("jwt")
        or (j.get("data") or {}).get("token")
    )

    if token:
        j["access_token"] = token

    return {
        "access_token": j.get("access_token"),
        "open_id": j.get("open_id"),
        "uid": j.get("uid"),
        "raw": j
    }

def encrypt_message(key, iv, plaintext):
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_message = pad(plaintext, AES.block_size)
    return cipher.encrypt(padded_message)

def decrypt_message(key, iv, ciphertext):
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(ciphertext)
    return unpad(decrypted, AES.block_size)

def safe_str(value):
    """Convert None to empty string, else return string value"""
    if value is None:
        return ""
    return str(value)

def process_token(uid, password):

    token_data = get_token(password, uid)

    if not token_data:
        return {"error": "Failed to retrieve token"}

    # Check if OAuth returned error
    if "error" in token_data and token_data["error"] != "OAuth non JSON":
        return {"error": token_data["error"], "raw": token_data.get("raw", {})}

    if "raw" in token_data:
        oauth_raw = token_data["raw"]
    else:
        oauth_raw = token_data

    # ---- GAME DATA ----
    game_data = my_pb2.GameData()
    game_data.timestamp = "2024-12-05 18:15:32"
    game_data.game_name = "free fire"
    game_data.game_version = 1
    game_data.version_code = "1.108.3"
    game_data.os_info = "Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)"
    game_data.device_type = "Handheld"
    game_data.network_provider = "Verizon Wireless"
    game_data.connection_type = "WIFI"
    game_data.screen_width = 1280
    game_data.screen_height = 960
    game_data.dpi = "240"
    game_data.cpu_info = "ARMv7 VFPv3 NEON VMH | 2400 | 4"
    game_data.total_ram = 5951
    game_data.gpu_name = "Adreno (TM) 640"
    game_data.gpu_version = "OpenGL ES 3.0"
    game_data.user_id = "Google|74b585a9-0268-4ad3-8f36-ef41d2e53610"
    game_data.ip_address = "172.190.111.97"
    game_data.language = "en"
    game_data.open_id = safe_str(token_data.get('open_id'))
    game_data.access_token = safe_str(token_data.get('access_token'))
    game_data.platform_type = 4
    game_data.device_form_factor = "Handheld"
    game_data.device_model = "Asus ASUS_I005DA"
    game_data.field_60 = 32968
    game_data.field_61 = 29815
    game_data.field_62 = 2479
    game_data.field_63 = 914
    game_data.field_64 = 31213
    game_data.field_65 = 32968
    game_data.field_66 = 31213
    game_data.field_67 = 32968
    game_data.field_70 = 4
    game_data.field_73 = 2
    game_data.library_path = "/data/app/com.dts.freefireth-QPvBnTUhYWE-7DMZSOGdmA==/lib/arm"
    game_data.field_76 = 1
    game_data.apk_info = "5b892aaabd688e571f688053118a162b|/data/app/com.dts.freefireth-QPvBnTUhYWE-7DMZSOGdmA==/base.apk"
    game_data.field_78 = 6
    game_data.field_79 = 1
    game_data.os_architecture = "32"
    game_data.build_number = "2019117877"
    game_data.field_85 = 1
    game_data.graphics_backend = "OpenGLES2"
    game_data.max_texture_units = 16383
    game_data.rendering_api = 4
    game_data.encoded_field_89 = "\\u0017T\\u0011\\u0017\\u0002\\b\\u000eUMQ\\bEZ\\u0003@ZK;Z\\u0002\\u000eV\\ri[QVi\\u0003\\ro\\t\\u0007e"
    game_data.field_92 = 9204
    game_data.marketplace = "3rd_party"
    game_data.encryption_key = "KqsHT2B4It60T/65PGR5PXwFxQkVjGNi+IMCK3CFBCBfrNpSUA1dZnjaT3HcYchlIFFL1ZJOg0cnulKCPGD3C3h1eFQ="
    game_data.total_storage = 111107
    game_data.field_97 = 1
    game_data.field_98 = 1
    game_data.field_99 = "4"
    game_data.field_100 = "4"

    serialized_data = game_data.SerializeToString()
    encrypted_data = encrypt_message(AES_KEY, AES_IV, serialized_data)

    url = "https://loginbp.ggblueshark.com/MajorLogin"
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/octet-stream",
        'Expect': "100-continue",
        'X-GA': "v1 1",
        'X-Unity-Version': "2018.4.11f1",
        'ReleaseVersion': "OB52"
    }

    try:
        response = requests.post(url, data=encrypted_data, headers=headers, verify=False)

        if response.status_code == 200:
            example_msg = output_pb2.Garena_420()
            example_msg.ParseFromString(response.content)

            # FIX: Access protobuf fields directly instead of parsing string
            # Based on output_pb2.py definition:
            # - token (field 8) = JWT token
            # - region (field 2) = region
            # - api (field 10) = api
            # - status (field 5) = status
            
            jwt_token = example_msg.token if example_msg.HasField("token") else "N/A"
            region = example_msg.region if example_msg.HasField("region") else "N/A"
            api = example_msg.api if example_msg.HasField("api") else "N/A"
            status = example_msg.status if example_msg.HasField("status") else "live"

            return {
                "token": jwt_token,
                "oauth_raw": oauth_raw,
                "api": api,
                "region": region,
                "status": status
            }
        else:
            return {"error": f"HTTP {response.status_code} - {response.reason}"}

    except Exception as e:
        return {"error": f"Request error: {e}"}

# ========== NEW FEATURE 1: Access Token se JWT Token ==========
@app.route('/jwt', methods=['GET'])
def get_jwt_from_access():
    """
    Access Token se JWT Token generate karo
    Usage: /jwt?access=YOUR_ACCESS_TOKEN
    """
    access_token = request.args.get('access')
    
    if not access_token:
        return jsonify({
            "error": "Missing parameter: access token required",
            "usage": "/jwt?access=YOUR_ACCESS_TOKEN"
        }), 400
    
    try:
        # Game data with provided access token
        game_data = my_pb2.GameData()
        game_data.timestamp = "2024-12-05 18:15:32"
        game_data.game_name = "free fire"
        game_data.game_version = 1
        game_data.version_code = "1.108.3"
        game_data.os_info = "Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)"
        game_data.device_type = "Handheld"
        game_data.network_provider = "Verizon Wireless"
        game_data.connection_type = "WIFI"
        game_data.screen_width = 1280
        game_data.screen_height = 960
        game_data.dpi = "240"
        game_data.cpu_info = "ARMv7 VFPv3 NEON VMH | 2400 | 4"
        game_data.total_ram = 5951
        game_data.gpu_name = "Adreno (TM) 640"
        game_data.gpu_version = "OpenGL ES 3.0"
        game_data.user_id = "Google|74b585a9-0268-4ad3-8f36-ef41d2e53610"
        game_data.ip_address = "172.190.111.97"
        game_data.language = "en"
        game_data.open_id = ""
        game_data.access_token = access_token
        game_data.platform_type = 4
        game_data.device_form_factor = "Handheld"
        game_data.device_model = "Asus ASUS_I005DA"
        game_data.field_60 = 32968
        game_data.field_61 = 29815
        game_data.field_62 = 2479
        game_data.field_63 = 914
        game_data.field_64 = 31213
        game_data.field_65 = 32968
        game_data.field_66 = 31213
        game_data.field_67 = 32968
        game_data.field_70 = 4
        game_data.field_73 = 2
        game_data.library_path = "/data/app/com.dts.freefireth-QPvBnTUhYWE-7DMZSOGdmA==/lib/arm"
        game_data.field_76 = 1
        game_data.apk_info = "5b892aaabd688e571f688053118a162b|/data/app/com.dts.freefireth-QPvBnTUhYWE-7DMZSOGdmA==/base.apk"
        game_data.field_78 = 6
        game_data.field_79 = 1
        game_data.os_architecture = "32"
        game_data.build_number = "2019117877"
        game_data.field_85 = 1
        game_data.graphics_backend = "OpenGLES2"
        game_data.max_texture_units = 16383
        game_data.rendering_api = 4
        game_data.encoded_field_89 = "\\u0017T\\u0011\\u0017\\u0002\\b\\u000eUMQ\\bEZ\\u0003@ZK;Z\\u0002\\u000eV\\ri[QVi\\u0003\\ro\\t\\u0007e"
        game_data.field_92 = 9204
        game_data.marketplace = "3rd_party"
        game_data.encryption_key = "KqsHT2B4It60T/65PGR5PXwFxQkVjGNi+IMCK3CFBCBfrNpSUA1dZnjaT3HcYchlIFFL1ZJOg0cnulKCPGD3C3h1eFQ="
        game_data.total_storage = 111107
        game_data.field_97 = 1
        game_data.field_98 = 1
        game_data.field_99 = "4"
        game_data.field_100 = "4"

        serialized_data = game_data.SerializeToString()
        encrypted_data = encrypt_message(AES_KEY, AES_IV, serialized_data)

        url = "https://loginbp.ggblueshark.com/MajorLogin"
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/octet-stream",
            'Expect': "100-continue",
            'X-GA': "v1 1",
            'X-Unity-Version': "2018.4.11f1",
            'ReleaseVersion': "OB52"
        }

        response = requests.post(url, data=encrypted_data, headers=headers, verify=False)

        if response.status_code == 200:
            example_msg = output_pb2.Garena_420()
            example_msg.ParseFromString(response.content)
            
            # FIX: Access fields directly from protobuf
            jwt_token = example_msg.token if example_msg.HasField("token") else "N/A"
            region = example_msg.region if example_msg.HasField("region") else "N/A"
            api = example_msg.api if example_msg.HasField("api") else "N/A"
            status = example_msg.status if example_msg.HasField("status") else "live"
            
            return jsonify({
                "jwt_token": jwt_token,
                "api": api,
                "region": region,
                "status": status,
                "input_access_token": access_token[:20] + "..." if len(access_token) > 20 else access_token
            })
        else:
            return jsonify({
                "error": f"HTTP {response.status_code} - {response.reason}",
                "raw_response": response.text[:500] if response.text else "No response"
            }), 500

    except Exception as e:
        return jsonify({"error": f"JWT generation error: {str(e)}"}), 500

# ========== NEW FEATURE 2: JWT Token se Access Token ==========
@app.route('/access', methods=['GET'])
def get_access_from_jwt():
    """
    JWT Token se Access Token validate karo
    Usage: /access?jwt=YOUR_JWT_TOKEN
    """
    jwt_token = request.args.get('jwt')
    
    if not jwt_token:
        return jsonify({
            "error": "Missing parameter: JWT token required",
            "usage": "/access?jwt=YOUR_JWT_TOKEN"
        }), 400
    
    try:
        # JWT validation endpoint (Garena token validation)
        validate_url = "https://ffmconnect.live.gop.garenanow.com/oauth/token/validate"
        
        headers = {
            "User-Agent": "GarenaMSDK/4.0.19P4(G011A ;Android 9;en;US;)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {jwt_token}"
        }
        
        data = {
            "access_token": jwt_token,
            "client_id": "100067",
            "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
        }
        
        # Pehle try karo direct validation
        try:
            r = requests.post(validate_url, headers=headers, data=data, timeout=10)
            if r.status_code == 200:
                validation_data = r.json()
                return jsonify({
                    "access_token": validation_data.get("access_token", jwt_token),
                    "open_id": validation_data.get("open_id", "N/A"),
                    "uid": validation_data.get("uid", "N/A"),
                    "token_type": validation_data.get("token_type", "bearer"),
                    "expires_in": validation_data.get("expires_in", "N/A"),
                    "validation_status": "valid",
                    "input_jwt": jwt_token[:30] + "..." if len(jwt_token) > 30 else jwt_token
                })
        except:
            pass
        
        # Agar validation fail ho toh JWT decode karke info do
        try:
            # JWT decode without verification (sirf info ke liye)
            parts = jwt_token.split('.')
            if len(parts) == 3:
                payload = parts[1]
                # Add padding if necessary
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += '=' * padding
                decoded_payload = base64.urlsafe_b64decode(payload)
                jwt_data = json.loads(decoded_payload)
                
                return jsonify({
                    "jwt_decoded_info": jwt_data,
                    "access_token": jwt_token,  # JWT hi access token ki tarah use hota hai
                    "note": "JWT decoded successfully. This JWT can be used as access token.",
                    "token_type": "JWT",
                    "input_jwt": jwt_token[:30] + "..." if len(jwt_token) > 30 else jwt_token
                })
            else:
                return jsonify({
                    "error": "Invalid JWT format",
                    "access_token": jwt_token,
                    "token_type": "Bearer"
                }), 400
                
        except Exception as decode_error:
            return jsonify({
                "error": f"JWT decode error: {str(decode_error)}",
                "access_token": jwt_token,
                "token_type": "Bearer"
            }), 500
            
    except Exception as e:
        return jsonify({"error": f"Access token retrieval error: {str(e)}"}), 500

# ========== ORIGINAL ENDPOINT (FIXED WITH JWT) ==========
@app.route('/token', methods=['GET'])
def get_token_response():

    uid = request.args.get('uid')
    password = request.args.get('password')

    if not uid or not password:
        return jsonify({"error": "Missing parameters: uid and password are required"}), 400

    result = process_token(uid, password)

    if "error" in result:
        return jsonify(result), 500

    # FIX: Explicitly include JWT token in response
    response_data = {
        "access_token": result.get("oauth_raw", {}).get("access_token") if isinstance(result.get("oauth_raw"), dict) else "N/A",
        "jwt_token": result.get("token"),  # Yeh hai game server se aaya JWT token!
        "api": result.get("api"),
        "region": result.get("region"),
        "status": result.get("status"),
        "oauth_raw": result.get("oauth_raw")
    }

    response = make_response(jsonify(response_data))
    response.headers["Content-Type"] = "application/json"
    return response

# ========== INFO ENDPOINT ==========
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "service": "Free Fire Token Service",
        "endpoints": {
            "/token?uid=&password=": "Get access token + JWT token (FIXED)",
            "/jwt?access=": "Convert Access Token to JWT Token (NEW)",
            "/access?jwt=": "Convert/Validate JWT Token to Access Token (NEW)"
        },
        "status": "running"
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
'''

print(fixed_final_code)