#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NELCPM1TOOLS — BULK CLONE ONLY
✅ 1 to 10 accounts ONLY — EXACTLY FROM MAIN.TXT
✅ WALANG TOKENS — LIBRE LAHAT
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
# CONFIG — FROM MAIN.TXT, WALANG PINAGBAGO
# ==============================================================
FIREBASE_URL = "https://newtoolcpm1-default-rtdb.firebaseio.com"
FIREBASE_SECRET = "xenPl7tYl28lkhZr9AOzUavzzIEP3nOh9h1WmWOj"
FK = "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM"

LOAD_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetPlayerRecords3"
SAVE_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/SavePlayerRecordsPartially8"
SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FK}"
LOGIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FK}"

app = Flask(__name__)
CORS(app)

# ==============================================================
# ENCRYPTION HELPERS — KATULAD SA MAIN.TXT
# ==============================================================
def make_xor_key(uid: str) -> bytes:
    chars = list(str(uid or ""))
    if len(chars) >= 9:
        chars[1], chars[8] = chars[8], chars[1]
    if len(chars) >= 3:
        chars.pop(2)
    if len(chars) >= 5:
        chars.append(chars[4])
    return "".join(chars).encode("utf-8") or b"0"

def xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))

def decompress(data: bytes):
    try:
        return brotli.decompress(data)
    except:
        try:
            return zlib.decompress(data, zlib.MAX_WBITS | 16)
        except:
            return None

def _md5(text: str) -> bytes:
    return hashlib.md5(str(text).encode()).digest()

def decrypt_aes(data: bytes, key: bytes):
    try:
        return unpad(AES.new(key[:16], AES.MODE_CBC, b"\x00" * 16).decrypt(data), 16)
    except:
        return None

# ==============================================================
# PLAYER PARSER — KATULAD SA MAIN.TXT
# ==============================================================
class Reader:
    def __init__(self, data: bytes):
        self.buf, self.pos = data, 0
    def read_byte(self):
        v = self.buf[self.pos] if self.pos + 1 <= len(self.buf) else 0
        self.pos += 1
        return v
    def read_int(self):
        if self.pos + 4 > len(self.buf): return 0
        v = struct.unpack_from("<i", self.buf, self.pos)[0]
        self.pos += 4
        return v
    def read_float(self):
        if self.pos + 4 > len(self.buf): return 0.0
        v = struct.unpack_from("<f", self.buf, self.pos)[0]
        self.pos += 4
        return v
    def read_string(self):
        marker = self.read_int()
        if marker in (0, -1): return ""
        length = (-marker) - 1 if marker < -1 else marker
        if marker < -1: self.read_int()
        length = max(0, min(length, 1000000))
        if self.pos + length > len(self.buf): return ""
        text = self.buf[self.pos:self.pos+length].decode("utf-8", errors="replace")
        self.pos += length
        return text.replace("\x00", "").strip()
    def read_list(self, item_fn):
        count = self.read_int()
        if count <= 0 or count > 1000000: return []
        res = []
        for _ in range(count):
            if self.pos >= len(self.buf): break
            val = item_fn()
            if val is not None: res.append(val)
        return res

def parse_player(buf: bytes):
    r = Reader(buf)
    if r.read_byte() == 0: return None
    return {
        "Name": r.read_string(),
        "money": r.read_int(),
        "coin": r.read_int(),
        "localID": r.read_string(),
        "boughtFsos": r.read_list(r.read_int),
        "FriendsID": r.read_list(lambda: r.read_string()),
        "LevelsDoneTime": r.read_list(r.read_float),
        "floats": r.read_list(r.read_float),
        "integers": r.read_list(r.read_int),
        "fcar": r.read_list(r.read_int),
        "favouriteWheels": r.read_list(r.read_int),
        "favouriteVinyls": r.read_list(r.read_string),
        "favouriteEmojis": r.read_list(r.read_int),
        "allData": r.read_string(),
        "flags": {},
        "animations": r.read_list(r.read_int),
        "emojiPacks": r.read_list(r.read_int),
        "wheels": r.read_list(r.read_int),
        "boughtPoliceLights": r.read_list(r.read_int),
        "boughtPoliceSirens": r.read_list(r.read_int),
        "boughtCars": r.read_list(r.read_int),
        "clothes": r.read_list(r.read_int),
        "interiors": r.read_list(r.read_int),
        "plates": r.read_list(r.read_string),
    }

def try_parse(buf: bytes):
    candidates = [buf, decompress(buf)]
    if candidates[1]: candidates.append(decompress(candidates[1]))
    for c in filter(None, candidates):
        if c[0] in (17, 23, 24):
            p = parse_player(c)
            if p and p.get("Name"): return p
        try:
            clean = c[3:] if len(c)>=3 and c[:2]==b"\xef\xbb" else c
            if clean and clean[0]==123: return json.loads(clean.decode())
        except: pass
    return None

def decrypt_record(b64_text: str, uid: str, password: str=None, email: str=None):
    try: buf = base64.b64decode(b64_text)
    except: return {"success":False,"message":"Bad base64"}
    direct = try_parse(buf)
    if direct: return {"success":True,"record":direct}
    if uid:
        dec = decompress(xor_bytes(buf, make_xor_key(uid)))
        if dec:
            p = try_parse(dec)
            if p: return {"success":True,"record":p}
    for key in [_md5("olzhas_carparking"), _md5(password or ""), _md5(uid), _md5(email or "")]:
        plain = decrypt_aes(buf, key)
        if plain:
            p = try_parse(plain)
            if p: return {"success":True,"record":p}
    return {"success":False,"message":"Decrypt failed"}

# ==============================================================
# WRITER — KATULAD SA MAIN.TXT
# ==============================================================
class Writer:
    def __init__(self): self._p = []
    def write_byte(self, v): self._p.append(bytes([int(v or 0) & 0xFF]))
    def write_int(self, v): self._p.append(struct.pack("<i", int(v or 0)))
    def write_float(self, v): self._p.append(struct.pack("<f", float(v or 0.0)))
    def write_string(self, s):
        if s is None: self.write_int(-1)
        elif s == "": self.write_int(0)
        else:
            enc = s.encode("utf-8")
            self.write_int(-(len(enc)) - 1)
            self.write_int(len(s))
            self._p.append(enc)
    def write_list(self, lst, fn):
        if lst is None: self.write_int(-1)
        else:
            self.write_int(len(lst))
            for item in lst: fn(item)
    def to_bytes(self): return b"".join(self._p)

FIELD_MAPPING = [
    (1, "localID"), (2, "money"), (3, "Name"), (4, "coin"), (5, "allData"),
    (6, "boughtFsos"), (7, "boughtPoliceLights"), (8, "boughtPoliceSirens"),
    (9, "FriendsID"), (10, "LevelsDoneTime"), (11, "floats"), (12, "integers"),
    (13, "fcar"), (14, "favouriteWheels"), (15, "favouriteVinyls"),
    (16, "favouriteEmojis"), (18, "emojiPacks"), (44, "animations"), (48, "wheels"),
    (50, "boughtCars"), (51, "clothes"), (52, "interiors")
]
INT_LIST = {6,7,8,12,13,14,16,18,44,48,50,51,52}
FLOAT_LIST = {10,11}

def serialize_field(fid: int, value):
    w = Writer()
    if fid in (1,3,5): w.write_string(value)
    elif fid in (2,4): w.write_int(value or 0)
    elif fid in INT_LIST: w.write_list(value or [], w.write_int)
    elif fid in FLOAT_LIST: w.write_list(value or [], w.write_float)
    else: return None
    return w.to_bytes()

def build_payload(record: dict, uid: str, fields: set):
    parts = [struct.pack("<i", len(fields))]
    for fid, key in FIELD_MAPPING:
        if key not in fields: continue
        raw = serialize_field(fid, record.get(key))
        if raw: parts.extend([struct.pack("<hi", fid, len(raw)), raw])
    combined = b"".join(parts)
    return base64.b64encode(xor_bytes(brotli.compress(combined), make_xor_key(uid))).decode("ascii")

# ==============================================================
# AUTH HELPERS — WALANG PINAGBAGO
# ==============================================================
def login_firebase(email: str, password: str):
    r = requests.post(LOGIN_URL, json={
        "email": email, "password": password, "returnSecureToken": True
    }, timeout=15)
    d = r.json()
    if "idToken" in d:
        return {"token": d["idToken"], "uid": d["localId"]}
    raise Exception(d.get("error", {}).get("message", "Login Failed"))

def create_random_account():
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
    email = f"cpmclone_{suffix}@gmail.com"
    password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%^&*"), k=14)
    
    r = requests.post(SIGNUP_URL, json={
        "email": email, "password": password, "returnSecureToken": True
    }, timeout=15)
    d = r.json()
    if "idToken" not in d:
        raise Exception(d.get("error", {}).get("message", "Signup Failed"))
    
    return {
        "email": email,
        "password": password,
        "uid": d["localId"],
        "token": d["idToken"]
    }

def load_player(uid: str, token: str, password: str, email: str):
    r = requests.post(LOAD_URL, json={"data": None}, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }, timeout=15)
    if not r.ok: raise Exception(f"Load failed: {r.status_code}")
    result = r.json()
    dec = decrypt_record(result["result"], uid, password, email)
    if not dec.get("success"): raise Exception(dec.get("message", "Decrypt Failed"))
    return dec["record"]

def save_player(uid: str, token: str, record: dict, fields: set):
    payload = build_payload(record, uid, fields)
    r = requests.post(SAVE_URL, json={
        "data": {"data": payload, "deviceId": uid[:8]}
    }, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }, timeout=15)
    return r.ok

# ==============================================================
# BULK CLONE — 1 TO 10 LANG!!!
# ==============================================================
@app.route('/bulk-clone', methods=['POST'])
def bulk_clone():
    try:
        d = request.json
        source_email = d.get("source_email")
        source_pass = d.get("source_pass")
        count = int(d.get("count", 1))
        
        if not source_email or not source_pass:
            return jsonify({"ok": False, "message": "Missing source credentials"})
        if count < 1 or count > 10:
            return jsonify({"ok": False, "message": "Count must be between 1 and 10 only"})
        
        src_auth = login_firebase(source_email, source_pass)
        src_data = load_player(src_auth["uid"], src_auth["token"], source_pass, source_email)
        
        if not src_data:
            return jsonify({"ok": False, "message": "Failed to load source account"})
        
        copy_fields = {
            "Name", "money", "coin", "localID", "boughtFsos", "FriendsID",
            "LevelsDoneTime", "floats", "integers", "fcar", "favouriteWheels",
            "favouriteVinyls", "favouriteEmojis", "allData", "animations",
            "emojiPacks", "wheels", "boughtPoliceLights", "boughtPoliceSirens",
            "boughtCars", "clothes", "interiors", "plates"
        }
        
        created_accounts = []
        failed = []
        
        for i in range(count):
            try:
                new_acc = create_random_account()
                save_player(new_acc["uid"], new_acc["token"], src_data, copy_fields)
                created_accounts.append({
                    "index": i + 1,
                    "email": new_acc["email"],
                    "password": new_acc["password"],
                    "uid": new_acc["uid"],
                    "cars_copied": len(src_data.get("fcar", []))
                })
            except Exception as e:
                failed.append({"index": i + 1, "error": str(e)})
        
        return jsonify({
            "ok": True,
            "source_email": source_email,
            "cars_copied": len(src_data.get("fcar", [])),
            "source_money": src_data.get("money", 0),
            "source_coins": src_data.get("coin", 0),
            "created_count": len(created_accounts),
            "failed_count": len(failed),
            "accounts": created_accounts,
            "errors": failed
        })
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"ok": True, "message": "Bulk Clone API Online"})

@app.route('/', methods=['GET'])
def home():
    return "<h1>✅ Bulk Clone API — 1-10 Accounts Only</h1>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
