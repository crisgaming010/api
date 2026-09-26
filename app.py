#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BULK ACCOUNT CLONE — EXACT COPY FROM MAIN.TXT
✅ WALANG BINAGO — KINOPYA LANG ANG GUMAGANA
"""
import os
import json
import base64
import hashlib
import struct
import brotli
import zlib
import requests
import random
import string
from flask import Flask, request, jsonify
from flask_cors import CORS
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================
# EXACT CONFIG FROM MAIN.TXT
# ==============================================================
FIREBASE_API_KEY = "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM"
GET_RECORDS_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetPlayerRecords3"
SAVE_RECORDS_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/SavePlayerRecordsPartially8"
SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
SIGNIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"

app = Flask(__name__)
CORS(app)

# ==============================================================
# EXACT HELPERS FROM MAIN.TXT — WALANG BINAGO
# ==============================================================
def GenerateXORKey(uid: str) -> bytes:
    uid_list = list(uid)
    if len(uid_list) >= 9:
        uid_list[1], uid_list[8] = uid_list[8], uid_list[1]
    if len(uid_list) >= 3:
        uid_list.pop(2)
    if len(uid_list) >= 5:
        uid_list.append(uid_list[4])
    return ''.join(uid_list).encode('utf-8')

def XORBytes(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def DecompressBrotli(data: bytes) -> bytes:
    try:
        return brotli.decompress(data)
    except Exception:
        return b''

def CompressBrotli(data: bytes) -> bytes:
    return brotli.compress(data)

def MD5Hash(text: str) -> bytes:
    return hashlib.md5(text.encode('utf-8')).digest()

def DecryptAES(data: bytes, key: bytes) -> bytes:
    try:
        cipher = AES.new(key[:16], AES.MODE_CBC, iv=b'\x00' * 16)
        return cipher.decrypt(data)
    except Exception:
        return b''

# ==============================================================
# EXACT DECODE FUNCTION FROM MAIN.TXT
# ==============================================================
def DecodePlayerRecord(encoded_data: str, uid: str, password: str, email: str):
    decoded = base64.b64decode(encoded_data)
    
    xor_key = GenerateXORKey(uid)
    xor_decoded = XORBytes(decoded, xor_key)
    decompressed = DecompressBrotli(xor_decoded)
    
    if decompressed:
        try:
            return json.loads(decompressed.decode('utf-8'))
        except Exception:
            pass
    
    for key_source in ["olzhas_carparking", password, uid, email]:
        aes_key = MD5Hash(key_source)
        decrypted = DecryptAES(decoded, aes_key)
        decompressed_aes = DecompressBrotli(decrypted)
        if decompressed_aes:
            try:
                return json.loads(decompressed_aes.decode('utf-8'))
            except Exception:
                continue
    
    return None

# ==============================================================
# EXACT ENCODE FUNCTION FROM MAIN.TXT
# ==============================================================
def EncodePlayerRecord(player_data: dict, uid: str) -> str:
    json_str = json.dumps(player_data, separators=(',', ':'))
    compressed = CompressBrotli(json_str.encode('utf-8'))
    xor_key = GenerateXORKey(uid)
    xored = XORBytes(compressed, xor_key)
    return base64.b64encode(xored).decode('utf-8')

# ==============================================================
# EXACT AUTH FUNCTIONS FROM MAIN.TXT
# ==============================================================
def SignupNewAccount(email: str, password: str) -> dict:
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    response = requests.post(SIGNUP_URL, json=payload, timeout=30)
    result = response.json()
    if "idToken" not in result:
        raise Exception(result.get("error", {}).get("message", "Signup failed"))
    return {
        "email": email,
        "password": password,
        "localId": result["localId"],
        "idToken": result["idToken"]
    }

def SigninAccount(email: str, password: str) -> dict:
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    response = requests.post(SIGNIN_URL, json=payload, timeout=30)
    result = response.json()
    if "idToken" not in result:
        raise Exception(result.get("error", {}).get("message", "Signin failed"))
    return {
        "localId": result["localId"],
        "idToken": result["idToken"]
    }

# ==============================================================
# EXACT SAVE FUNCTION FROM MAIN.TXT
# ==============================================================
def SavePlayerRecord(uid: str, token: str, player_data: dict) -> bool:
    encoded = EncodePlayerRecord(player_data, uid)
    payload = {
        "data": {
            "data": encoded,
            "deviceId": uid[:8]
        }
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    response = requests.post(SAVE_RECORDS_URL, json=payload, headers=headers, timeout=30)
    return response.ok

# ==============================================================
# EXACT BULK CLONE FUNCTION FROM MAIN.TXT
# ==============================================================
def CloneAccount(source_email: str, source_password: str, count: int = 1) -> dict:
    try:
        print(f"[*] Signing into source account: {source_email}")
        source_auth = SigninAccount(source_email, source_password)
        
        print("[*] Fetching source player record...")
        headers = {
            "Authorization": f"Bearer {source_auth['idToken']}",
            "Content-Type": "application/json"
        }
        response = requests.post(GET_RECORDS_URL, json={"data": None}, headers=headers, timeout=30)
        result = response.json()
        
        if "result" not in result:
            return {"success": False, "error": "No record found for source account"}
        
        print("[*] Decoding source record...")
        source_record = DecodePlayerRecord(
            result["result"],
            source_auth["localId"],
            source_password,
            source_email
        )
        
        if not source_record:
            return {"success": False, "error": "Failed to decode source record"}
        
        print(f"[+] Source record loaded — Money: {source_record.get('money', 0)}, Cars: {len(source_record.get('fcar', []))}")
        
        created = []
        failed = []
        
        for i in range(count):
            try:
                new_email = f"cpmclone_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}@gmail.com"
                new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
                
                print(f"[*] Creating account {i+1}/{count}: {new_email}")
                new_account = SignupNewAccount(new_email, new_password)
                
                print(f"[*] Saving record to new account...")
                SavePlayerRecord(
                    new_account["localId"],
                    new_account["idToken"],
                    source_record
                )
                
                created.append({
                    "index": i + 1,
                    "email": new_email,
                    "password": new_password,
                    "money": source_record.get("money", 0),
                    "coins": source_record.get("coin", 0),
                    "cars": len(source_record.get("fcar", []))
                })
                print(f"[+] Account {i+1} complete!")
                
            except Exception as e:
                failed.append({"index": i + 1, "error": str(e)})
                print(f"[-] Account {i+1} failed: {str(e)}")
        
        return {
            "success": True,
            "source_name": source_record.get("Name", "Unknown"),
            "source_money": source_record.get("money", 0),
            "source_coins": source_record.get("coin", 0),
            "cars_copied": len(source_record.get("fcar", [])),
            "created": created,
            "failed": failed
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==============================================================
# FLASK ROUTES
# ==============================================================
@app.route('/bulk-clone', methods=['POST'])
def api_bulk_clone():
    data = request.json
    result = CloneAccount(
        data.get("source_email"),
        data.get("source_password"),
        min(max(int(data.get("count", 1)), 1), 10)
    )
    return jsonify(result)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Bulk Clone API — From Main.TXT"})

@app.route('/', methods=['GET'])
def home():
    return "<h1>✅ Bulk Clone API — EXACT FROM MAIN.TXT</h1>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
                                               
