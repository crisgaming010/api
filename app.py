#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NELCPM1TOOLS V25.0 — BACKEND SERVER
All game API logic here. HTML talks to this, this talks to game API.
"""
import os
import json
import time
import uuid
import base64
import hashlib
import random
import re
import string
import struct
import zlib
import brotli
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==============================================================
# CONFIG — THESE ARE SECRETS, KEEP IN .env ON RENDER
# ==============================================================
FIREBASE_URL = os.environ.get("FIREBASE_URL", "https://newtoolcpm1-default-rtdb.firebaseio.com")
FIREBASE_SECRET = os.environ.get("FIREBASE_SECRET", "xenPl7tYl28lkhZr9AOzUavzzIEP3nOh9h1WmWOj")
FK = os.environ.get("FIREBASE_API_KEY", "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM")

LOAD_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetPlayerRecords3"
SAVE_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/SavePlayerRecordsPartially8"
RANK_URL = "https://us-central1-cp-multiplayer.cloudfunctions.net/SetUserRating5"
CARS_FETCH_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetAllCars2"
CARS_SAVE_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/SaveCarsPartially8"

MAX_MONEY = 50_000_000
MAX_COIN = 500_000
PREMIUM_TOKEN_THRESHOLD = 50

TOKEN_COSTS = {
    "unlock": 20,
    "unlock_all": 75,
    "clone_single": 90,
    "bulk_1_5": 120,
    "bulk_6_10": 150,
}

USD_TO_PHP = 62.0

app = Flask(__name__)
CORS(app)  # Allow HTML to talk to backend

# ==============================================================
# FIREBASE HELPERS
# ==============================================================
def fb_get(path):
    try:
        url = f"{FIREBASE_URL}/{path}.json?auth={FIREBASE_SECRET}"
        r = requests.get(url, timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[FB GET ERROR] {e}")
        return None

def fb_patch(path, data):
    try:
        url = f"{FIREBASE_URL}/{path}.json?auth={FIREBASE_SECRET}"
        r = requests.patch(url, json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[FB PATCH ERROR] {e}")
        return False

def fb_put(path, data):
    try:
        url = f"{FIREBASE_URL}/{path}.json?auth={FIREBASE_SECRET}"
        r = requests.put(url, json=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[FB PUT ERROR] {e}")
        return False

def get_user_by_email(email):
    data = fb_get("cpm1_users")
    if not data:
        return None
    for uid, user in data.items():
        if user.get("username") == email or user.get("email") == email:
            return {"uid": uid, **user}
    # Fallback: search by email field
    for uid, user in data.items():
        if user.get("email") == email:
            return {"uid": uid, **user}
    return None

def get_or_create_user(email):
    user = get_user_by_email(email)
    if not user:
        uid = str(uuid.uuid4())
        fb_put(f"cpm1_users/{uid}", {
            "email": email,
            "tokens": 0,
            "premium_by_tokens": False,
            "warnings": 0,
            "banned": False,
            "joined": datetime.now().isoformat()
        })
        user = {"uid": uid, "email": email, "tokens": 0, "premium_by_tokens": False}
    return user

def has_enough_tokens(user_email, amount):
    user = get_or_create_user(user_email)
    return user.get("tokens", 0) >= amount

def deduct_tokens(user_email, amount):
    user = get_or_create_user(user_email)
    current = user.get("tokens", 0)
    if current < amount:
        return False
    new_balance = current - amount
    fb_patch(f"cpm1_users/{user['uid']}", {"tokens": new_balance})
    # Check premium expiry
    if user.get("premium_by_tokens") and new_balance <= PREMIUM_TOKEN_THRESHOLD:
        fb_patch(f"cpm1_users/{user['uid']}", {"premium_by_tokens": False})
    return True

def add_tokens(user_email, amount):
    user = get_or_create_user(user_email)
    current = user.get("tokens", 0)
    fb_patch(f"cpm1_users/{user['uid']}", {"tokens": current + amount})

def is_premium_user(email):
    user = get_or_create_user(email)
    if user.get("premium_by_tokens") and user.get("tokens", 0) > PREMIUM_TOKEN_THRESHOLD:
        return True
    # Check subscription expiry
    sub = user.get("subscription")
    if sub and sub.get("premium_expiry"):
        try:
            if datetime.fromisoformat(sub["premium_expiry"]) > datetime.now():
                return True
        except:
            pass
    return False

# ==============================================================
# GAME API HELPERS — ENCRYPTION / DECRYPTION
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
        pass
    try:
        return zlib.decompress(data, zlib.MAX_WBITS | 16)
    except:
        pass
    return None

def _md5(text: str) -> bytes:
    return hashlib.md5(str(text).encode()).digest()

def _sha1(text: str) -> bytes:
    return hashlib.sha1(str(text).encode()).digest()[:16]

def build_aes_keys(uid: str, password: str = None, email: str = None):
    keys = [_md5("olzhas_carparking")]
    if password:
        keys.extend([_md5(password), _sha1(password)])
    if uid:
        keys.extend([_md5(uid), _sha1(uid)])
    if email:
        keys.append(_md5(email))
    return keys

def decrypt_aes(data: bytes, key: bytes):
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        return unpad(AES.new(key[:16], AES.MODE_CBC, b"\x00" * 16).decrypt(data), 16)
    except:
        return None

# ==============================================================
# PLAYER PARSER
# ==============================================================
class Reader:
    def __init__(self, data: bytes):
        self.buf, self.pos = data, 0
    def has_bytes(self, n: int) -> bool:
        return self.pos + n <= len(self.buf)
    def read_byte(self) -> int:
        v = self.buf[self.pos] if self.has_bytes(1) else 0
        self.pos += 1
        return v
    def read_int(self) -> int:
        if not self.has_bytes(4):
            return 0
        v = struct.unpack_from("<i", self.buf, self.pos)[0]
        self.pos += 4
        return v
    def read_float(self) -> float:
        if not self.has_bytes(4):
            return 0.0
        v = struct.unpack_from("<f", self.buf, self.pos)[0]
        self.pos += 4
        return v
    def read_string(self) -> str:
        marker = self.read_int()
        if marker in (0, -1):
            return ""
        length = (-marker) - 1 if marker < -1 else marker
        if marker < -1:
            self.read_int()
        length = max(0, min(length, 1000000))
        if not self.has_bytes(length):
            return ""
        text = self.buf[self.pos:self.pos + length].decode("utf-8", errors="replace")
        self.pos += length
        return text.replace("\x00", "").strip()
    def read_list(self, item_fn):
        count = self.read_int()
        if count <= 0 or count > 1000000:
            return []
        res = []
        for _ in range(count):
            if self.pos >= len(self.buf):
                break
            val = item_fn()
            if val is not None:
                res.append(val)
        return res

def parse_player(buf: bytes) -> dict:
    r = Reader(buf)
    if r.read_byte() == 0:
        return None
    player = {
        "Name": r.read_string(),
        "money": r.read_int(),
        "coin": r.read_int(),
        "localID": r.read_string(),
        "boughtFsos": r.read_list(r.read_int)
    }
    player["FriendsID"] = r.read_list(lambda: (r.read_byte(), {
        "id": r.read_string(), "Name": r.read_string(), "accountID": r.read_string()
    })[1])
    player.update({
        "LevelsDoneTime": r.read_list(r.read_float),
        "floats": r.read_list(r.read_float),
        "integers": r.read_list(r.read_int),
        "fcar": r.read_list(r.read_int),
        "favouriteWheels": r.read_list(r.read_int),
        "favouriteVinyls": r.read_list(r.read_string),
        "favouriteEmojis": r.read_list(r.read_int),
    })
    player["allData"] = r.read_string()
    player["flags"] = {}
    count = r.read_int()
    for _ in range(count):
        k = r.read_int()
        v = r.read_int()
        player["flags"][k] = v
    player["animations"] = r.read_list(r.read_int)
    player["emojiPacks"] = r.read_list(r.read_int)
    player["wheels"] = r.read_list(r.read_int)
    player["boughtPoliceLights"] = r.read_list(r.read_int)
    player["boughtPoliceSirens"] = r.read_list(r.read_int)
    return player

def try_parse(buf: bytes) -> dict:
    candidates = [buf, decompress(buf)]
    if candidates[1]:
        candidates.append(decompress(candidates[1]))
    for candidate in filter(None, candidates):
        if candidate[0] in (17, 23, 24):
            try:
                p = parse_player(candidate)
                if p and p.get("Name") is not None:
                    return p
            except:
                pass
        try:
            clean = candidate[3:] if len(candidate) >= 3 and candidate[:2] == b"\xef\xbb" else candidate
            if clean and clean[0] == 123:
                return json.loads(clean.decode("utf-8"))
        except:
            pass
    return None

def decrypt_player_record(base64_text: str, uid: str, password: str = None, email: str = None) -> dict:
    try:
        buf = base64.b64decode(base64_text)
    except:
        return {"success": False, "message": "Bad base64"}
    if len(buf) < 10:
        return {"success": False, "message": "Too small"}
    direct = try_parse(buf)
    if direct:
        return {"success": True, "record": direct}
    if uid:
        try:
            decoded = decompress(xor_bytes(buf, make_xor_key(uid)))
            if decoded:
                parsed = try_parse(decoded)
                if parsed:
                    return {"success": True, "record": parsed}
        except:
            pass
    for key in build_aes_keys(uid or "", password, email):
        plain = decrypt_aes(buf, key)
        if not plain:
            continue
        parsed = try_parse(plain)
        if parsed:
            return {"success": True, "record": parsed}
    return {"success": False, "message": "Could not decrypt"}

# ==============================================================
# PLAYER WRITER
# ==============================================================
class Writer:
    def __init__(self):
        self._p = []
    def write_byte(self, v):
        self._p.append(bytes([int(v or 0) & 0xFF]))
    def write_int(self, v):
        self._p.append(struct.pack("<i", int(v or 0)))
    def write_float(self, v):
        self._p.append(struct.pack("<f", float(v or 0.0)))
    def write_string(self, s):
        if s is None:
            self._p.append(struct.pack("<i", -1))
            return
        s = str(s)
        if s == "":
            self._p.append(struct.pack("<i", 0))
            return
        enc = s.encode("utf-8")
        self._p.append(struct.pack("<ii", -(len(enc)) - 1, len(s)) + enc)
    def write_list(self, lst, fn):
        if lst is None:
            self._p.append(struct.pack("<i", -1))
            return
        self._p.append(struct.pack("<i", len(lst)))
        for item in lst:
            fn(item)
    def to_bytes(self):
        return b"".join(self._p)

FIELD_MAPPING = [
    (1, "localID"), (2, "money"), (3, "Name"), (4, "coin"), (5, "allData"),
    (6, "boughtFsos"), (7, "boughtPoliceLights"), (8, "boughtPoliceSirens"),
    (9, "FriendsID"), (10, "LevelsDoneTime"), (11, "floats"), (12, "integers"),
    (13, "fcar"), (14, "favouriteWheels"), (15, "favouriteVinyls"),
    (16, "favouriteEmojis"), (18, "emojiPacks"), (44, "animations"), (48, "wheels")
]
INT_LIST_FIELDS = {6, 7, 8, 12, 13, 14, 16, 18, 44, 48}
FLOAT_LIST_FIELDS = {10, 11}

def serialize_field(fid: int, value):
    w = Writer()
    if fid in (1, 3, 5):
        w.write_string(value)
        return w.to_bytes()
    if fid in (2, 4):
        w.write_int(value or 0)
        return w.to_bytes()
    if fid in INT_LIST_FIELDS:
        w.write_list(value or [], w.write_int)
        return w.to_bytes()
    if fid in FLOAT_LIST_FIELDS:
        w.write_list(value or [], w.write_float)
        return w.to_bytes()
    return None

def build_payload(record: dict, uid: str, force_fields: set = None) -> str:
    force_fields = force_fields or set()
    fields = []
    for fid, key in FIELD_MAPPING:
        value = record.get(key)
        if value is None:
            continue
        if key == "allData" and not isinstance(value, str):
            continue
        if key not in force_fields and key != "allData":
            continue
        raw = serialize_field(fid, value)
        if raw:
            fields.append((fid, raw))
    parts = [struct.pack("<i", len(fields))]
    for fid, raw in fields:
        parts.extend([struct.pack("<hi", fid, len(raw)), raw])
    combined = b"".join(parts)
    compressed = brotli.compress(combined)
    encrypted = xor_bytes(compressed, make_xor_key(uid))
    return base64.b64encode(encrypted).decode("ascii")

# ==============================================================
# GAME API CLIENT
# ==============================================================
class CPMClient:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.token = None
        self.fuid = None
        self._login()

    def _login(self):
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FK}"
        resp = requests.post(url, json={
            "email": self.email,
            "password": self.password,
            "returnSecureToken": True,
            "clientType": "CLIENT_TYPE_ANDROID"
        }, timeout=15)
        data = resp.json()
        if "idToken" in data:
            self.token = data["idToken"]
            self.fuid = data["localId"]
            return True
        raise Exception(data.get("error", {}).get("message", "LOGIN_FAILED"))

    def _headers(self):
        return {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "UnityPlayer/2022.3.62f2",
            "X-Unity-Version": "2022.3.62f2",
        }

    def load_profile(self):
        resp = requests.post(LOAD_URL, json={"data": None}, headers=self._headers(), timeout=15)
        if not resp.ok:
            raise Exception(f"LOAD_FAILED: {resp.status_code}")
        result = resp.json()
        if "result" not in result:
            raise Exception("NO_RESULT")
        dec = decrypt_player_record(result["result"], self.fuid, self.password, self.email)
        if not dec.get("success"):
            raise Exception(dec.get("message", "DECRYPT_FAILED"))
        return dec["record"]

    def save_profile(self, record: dict, force_fields: set):
        payload = build_payload(record, self.fuid, force_fields=force_fields)
        resp = requests.post(SAVE_URL, json={
            "data": {"data": payload, "deviceId": self.fuid[:8]}
        }, headers=self._headers(), timeout=15)
        return resp.ok

    def set_rank(self):
        rating_data = {
            "RatingData": {
                "time": 1e22, "cars": 1e16, "car_fix": 1e13, "car_collided": 1e12,
                "car_exchange": 1e13, "car_trade": 1e13, "car_wash": 1e13,
                "slicer_cut": 1e13, "drift_max": 1e14, "drift": 1e14,
                "race_win": 3e20, "levels": 10000990000
            }
        }
        requests.post(RANK_URL, json={"data": json.dumps(rating_data)}, headers=self._headers(), timeout=15)
        return True

# ==============================================================
# FEATURE IMPLEMENTATIONS
# ==============================================================
def set_float_field(client: CPMClient, index: int, value: float):
    rec = client.load_profile()
    floats = rec.get("floats", [])
    while len(floats) <= index:
        floats.append(0.0)
    floats[index] = value
    rec["floats"] = floats
    client.save_profile(rec, {"floats"})
    return True

def set_int_field(client: CPMClient, index: int, value: int):
    rec = client.load_profile()
    ints = rec.get("integers", [])
    while len(ints) <= index:
        ints.append(0)
    ints[index] = value
    rec["integers"] = ints
    client.save_profile(rec, {"integers"})
    return True

def unlock_feature(client: CPMClient, feature: str):
    rec = client.load_profile()
    if feature == "w16":
        return set_float_field(client, 32, 1.0)
    elif feature == "horns":
        for i in range(27, 32):
            set_float_field(client, i, 1.0)
        return True
    elif feature == "damage":
        return set_float_field(client, 34, 1.0)
    elif feature == "fuel":
        return set_float_field(client, 3, 1.0)
    elif feature == "smoke":
        return set_float_field(client, 33, 1.0)
    elif feature == "animations":
        rec["animations"] = sorted(set(rec.get("animations", []) + list(range(301))))
        client.save_profile(rec, {"animations"})
        return True
    elif feature == "wheels":
        rec["wheels"] = sorted(set(rec.get("wheels", []) + list(range(73, 221))))
        ints = rec.get("integers", [])
        while len(ints) < 113:
            int
