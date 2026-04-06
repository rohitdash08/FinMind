"""Client-side AES-256-GCM encryption (issue #99)."""
import base64, hashlib, hmac, json, secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)

def encrypt_payload(data: dict, key: bytes) -> dict:
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, json.dumps(data).encode(), None)
    return {"ciphertext": base64.b64encode(ct).decode(), "nonce": base64.b64encode(nonce).decode(), "version": 1}

def decrypt_payload(enc: dict, key: bytes) -> dict:
    return json.loads(AESGCM(key).decrypt(base64.b64decode(enc["nonce"]), base64.b64decode(enc["ciphertext"]), None))

def encrypt_field(value: str, key: bytes) -> str:
    return json.dumps(encrypt_payload({"v": value}, key))

def decrypt_field(s: str, key: bytes) -> str:
    return decrypt_payload(json.loads(s), key)["v"]

def sign_data(data: dict, secret: bytes) -> str:
    return hmac.new(secret, json.dumps(data, sort_keys=True).encode(), hashlib.sha256).hexdigest()
