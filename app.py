#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BULK CLONE — EXACT FROM MAIN.TXT + FRONTEND COMPATIBLE
✅ FIXED: Returns EXACT format frontend expects — no more "undefined"
"""
import os
import json
import base64
import hashlib
import brotli
import random
import string
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================
# CONFIG — EXACT
# ==============================================================
FIREBASE_API_KEY = "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM"
GET_RECORDS_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetPlayerRecords3"
SAVE_RECORDS_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/SavePlayerRecordsPartially8"
SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
SIGNIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"

app = Flask(__name__)
CORS(app)

# ==============================================================
# HELPERS — EXACT FROM MAIN.TXT
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

# ==============================================================
# DECODE / ENCODE — EXACT
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
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
            cipher = AES.new(aes_key[:16], AES.MODE_CBC, iv=b'\x00' * 16)
            decrypted = cipher.decrypt(decoded)
            decompressed_aes = DecompressBrotli(decrypted)
            if decompressed_aes:
                try:
                    return json.loads(decompressed_aes.decode('utf-8'))
                except Exception:
                    continue
        except:
            continue
    return None

def EncodePlayerRecord(player_data: dict, uid: str) -> str:
    json_str = json.dumps(player_data, separators=(',', ':'))
    compressed = CompressBrotli(json_str.encode('utf-8'))
    xor_key = GenerateXORKey(uid)
    xored = XORBytes(compressed, xor_key)
    return base64.b64encode(xored).decode('utf-8')

# ==============================================================
# AUTH — EXACT
# ==============================================================
def SignupNewAccount(email: str, password: str) -> dict:
    payload = {"email": email, "password": password, "returnSecureToken": True}
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
    payload = {"email": email, "password": password, "returnSecureToken": True}
    response = requests.post(SIGNIN_URL, json=payload, timeout=30)
    result = response.json()
    if "idToken" not in result:
        raise Exception(result.get("error", {}).get("message", "Signin failed"))
    return {"localId": result["localId"], "idToken": result["idToken"]}

def SavePlayerRecord(uid: str, token: str, player_data: dict) -> bool:
    encoded = EncodePlayerRecord(player_data, uid)
    payload = {"data": {"data": encoded, "deviceId": uid[:8]}}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(SAVE_RECORDS_URL, json=payload, headers=headers, timeout=30)
    return response.ok

# ==============================================================
# ✅ BULK CLONE — FRONTEND COMPATIBLE RESPONSE
# ==============================================================
@app.route('/bulk-clone', methods=['POST'])
def bulk_clone():
    try:
        data = request.json
        source_email = data.get("source_email")
        source_password = data.get("source_password")
        count = min(max(int(data.get("count", 1)), 1), 10)

        if not source_email or not source_password:
            return jsonify({"ok": False, "message": "Missing source credentials"})

        # 1. Login source
        source_auth = SigninAccount(source_email, source_password)

        # 2. Load source record
        headers = {"Authorization": f"Bearer {source_auth['idToken']}", "Content-Type": "application/json"}
        response = requests.post(GET_RECORDS_URL, json={"data": None}, headers=headers, timeout=30)
        result = response.json()

        if "result" not in result:
            return jsonify({"ok": False, "message": "No record found for source account"})

        source_record = DecodePlayerRecord(
            result["result"],
            source_auth["localId"],
            source_password,
            source_email
        )

        if not source_record:
            return jsonify({"ok": False, "message": "Failed to decode source record — check password"})

        cars_list = source_record.get("fcar", [])
        money_val = source_record.get("money", 0)
        coins_val = source_record.get("coin", 0)
        source_name = source_record.get("Name", "Unknown")

        created_accounts = []
        failed_count = 0

        for i in range(count):
            try:
                new_email = f"cpmclone_{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}@gmail.com"
                new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

                new_acc = SignupNewAccount(new_email, new_password)
                SavePlayerRecord(new_acc["localId"], new_acc["idToken"], source_record)

                created_accounts.append({
                    "index": i + 1,
                    "email": new_email,
                    "password": new_password,
                    "cars_copied": len(cars_list)
                })
            except Exception as e:
                failed_count += 1
                print(f"Account {i+1} failed: {e}")

        return jsonify({
            "ok": True,
            "source_name": source_name,
            "source_email": source_email,
            "cars_copied": len(cars_list),
            "source_money": money_val,
            "source_coins": coins_val,
            "created_count": len(created_accounts),
            "failed_count": failed_count,
            "accounts": created_accounts
        })

    except Exception as e:
        print(f"API Error: {str(e)}")
        return jsonify({"ok": False, "message": str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"ok": True, "message": "Bulk Clone API Online"})

@app.route('/', methods=['GET'])
def home():
    return "<h1>✅ Bulk Clone API — Online</h1>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
        
