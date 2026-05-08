"""Decrypt and encrypt Granola's encrypted storage files (Windows).

Granola 2.x switched to encrypted local storage (supabase.json.enc, etc.).
The encryption scheme is Electron's safeStorage on Windows:

  Local State.os_crypt.encrypted_key
    -> base64 decode
    -> strip "DPAPI" 5-byte prefix
    -> CryptUnprotectData (DPAPI)
    -> 32-byte master AES key

  storage.dek
    -> "v10" prefix(3) + iv(12) + ciphertext + tag(16)
    -> AES-256-GCM decrypt with master key
    -> base64 string -> 32-byte DEK

  *.enc files
    -> iv(12) + ciphertext + tag(16)
    -> AES-256-GCM decrypt with DEK
    -> JSON utf-8

Constants and format match Granola's app.asar (IV_LEN=12, TAG_LEN=16, DEK_LEN=32).
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

IV_LEN = 12
TAG_LEN = 16
DPAPI_PREFIX = b"DPAPI"
V10_PREFIX = b"v10"


def is_supported() -> bool:
    """Encrypted storage decryption only supported on Windows."""
    return sys.platform == "win32"


def _get_master_key(granola_dir: Path) -> bytes:
    """Decrypt the OS-bound master key from Local State."""
    import win32crypt

    local_state = json.loads((granola_dir / "Local State").read_text(encoding="utf-8"))
    encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    if not encrypted_key.startswith(DPAPI_PREFIX):
        raise ValueError("Local State encrypted_key missing DPAPI prefix")
    _desc, master_key = win32crypt.CryptUnprotectData(
        encrypted_key[len(DPAPI_PREFIX):], None, None, None, 0
    )
    return master_key


def _get_dek(granola_dir: Path, master_key: bytes) -> bytes:
    """Decrypt the per-app DEK from storage.dek."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    blob = (granola_dir / "storage.dek").read_bytes()
    if not blob.startswith(V10_PREFIX):
        raise ValueError("storage.dek missing v10 prefix")
    body = blob[len(V10_PREFIX):]
    iv, ct_and_tag = body[:IV_LEN], body[IV_LEN:]
    dek_b64 = AESGCM(master_key).decrypt(iv, ct_and_tag, None)
    return base64.b64decode(dek_b64)


def get_dek(granola_dir: Path) -> bytes:
    """Return the 32-byte AES DEK used to encrypt Granola's *.enc files."""
    if not is_supported():
        raise RuntimeError("Encrypted Granola storage is only supported on Windows")
    master_key = _get_master_key(granola_dir)
    return _get_dek(granola_dir, master_key)


def decrypt_file(enc_path: Path, dek: bytes) -> bytes:
    """Decrypt a Granola *.enc file (iv || ciphertext || tag)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    blob = enc_path.read_bytes()
    iv, ct_and_tag = blob[:IV_LEN], blob[IV_LEN:]
    return AESGCM(dek).decrypt(iv, ct_and_tag, None)


def encrypt_bytes(plaintext: bytes, dek: bytes) -> bytes:
    """Encrypt plaintext into the iv || ciphertext || tag layout used by Granola."""
    import os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    iv = os.urandom(IV_LEN)
    ct_and_tag = AESGCM(dek).encrypt(iv, plaintext, None)
    return iv + ct_and_tag
