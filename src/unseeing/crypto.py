"""Password-based vault encryption using only the standard library.

This is a convenience lock for a mapping file on disk: PBKDF2-HMAC-SHA256,
a SHA-256 counter keystream, and HMAC-SHA256 (encrypt-then-MAC). It is not
a substitute for an HSM, KMS, or a dedicated secret store.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from unseeing.errors import VaultError

MAGIC = b"UNSEE1"
_SALT_LEN = 16
_NONCE_LEN = 16
_MAC_LEN = 32
_ITERATIONS = 200_000


def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS, dklen=32)


def _keystream_xor(data: bytes, key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    counter = 0
    offset = 0
    while offset < len(data):
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        take = min(len(block), len(data) - offset)
        out.extend(a ^ b for a, b in zip(data[offset : offset + take], block[:take], strict=False))
        offset += take
        counter += 1
    return bytes(out)


def encrypt(plaintext: bytes, password: str) -> bytes:
    salt = secrets.token_bytes(_SALT_LEN)
    nonce = secrets.token_bytes(_NONCE_LEN)
    key = derive_key(password, salt)
    ciphertext = _keystream_xor(plaintext, key, nonce)
    mac = hmac.new(key, MAGIC + salt + nonce + ciphertext, hashlib.sha256).digest()
    return MAGIC + salt + nonce + ciphertext + mac


def decrypt(blob: bytes, password: str) -> bytes:
    header_len = len(MAGIC) + _SALT_LEN + _NONCE_LEN
    if len(blob) < header_len + _MAC_LEN or not blob.startswith(MAGIC):
        raise VaultError("not an unseeing vault (missing UNSEE1 header)")
    salt = blob[len(MAGIC) : len(MAGIC) + _SALT_LEN]
    nonce = blob[len(MAGIC) + _SALT_LEN : header_len]
    mac = blob[-_MAC_LEN:]
    ciphertext = blob[header_len:-_MAC_LEN]
    key = derive_key(password, salt)
    expected = hmac.new(key, MAGIC + salt + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise VaultError("invalid vault password or corrupted file")
    return _keystream_xor(ciphertext, key, nonce)
