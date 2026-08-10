"""Tests for credential loading (double-JSON, .enc preference, fallback)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from granola_sync.auth import credentials, encrypted_storage


def _write_supabase(path: Path, workos: dict | None = None, cognito: dict | None = None) -> None:
    raw: dict = {}
    if workos is not None:
        raw["workos_tokens"] = json.dumps(workos)  # stored as a JSON *string*
    if cognito is not None:
        raw["cognito_tokens"] = json.dumps(cognito)
    path.write_text(json.dumps(raw), encoding="utf-8")


_WORKOS = {
    "access_token": "at-plain",
    "refresh_token": "rt-plain",
    "expires_in": 21600,
    "obtained_at": 111,
}


def test_load_parses_double_json_workos(tmp_path: Path):
    path = tmp_path / "supabase.json"
    _write_supabase(path, workos=_WORKOS)
    tokens = credentials.load_credentials(path)
    assert tokens.access_token == "at-plain"
    assert tokens.refresh_token == "rt-plain"


def test_load_falls_back_to_cognito(tmp_path: Path):
    path = tmp_path / "supabase.json"
    _write_supabase(
        path,
        cognito={"access_token": "at-cog", "refresh_token": "rt-cog", "expires_in": 86400},
    )
    tokens = credentials.load_credentials(path)
    assert tokens.access_token == "at-cog"
    assert tokens.obtained_at == 0  # cognito default → triggers 401-based refresh


def test_prefers_enc_when_newer(tmp_path: Path, monkeypatch):
    path = tmp_path / "supabase.json"
    _write_supabase(path, workos=_WORKOS)  # plaintext has at-plain

    enc_path = path.with_name(path.name + ".enc")
    enc_path.write_bytes(b"ciphertext")

    # Make the .enc newer than the plaintext file.
    os.utime(path, (1000, 1000))
    os.utime(enc_path, (2000, 2000))

    newer = {**_WORKOS, "access_token": "at-enc", "obtained_at": 222}
    monkeypatch.setattr(encrypted_storage, "is_supported", lambda: True)
    monkeypatch.setattr(encrypted_storage, "get_dek", lambda _dir: b"dek")
    monkeypatch.setattr(
        encrypted_storage,
        "decrypt_file",
        lambda _p, _dek: json.dumps({"workos_tokens": json.dumps(newer)}).encode(),
    )

    tokens = credentials.load_credentials(path)
    assert tokens.access_token == "at-enc"


def test_falls_back_to_plaintext_on_decrypt_error(tmp_path: Path, monkeypatch):
    path = tmp_path / "supabase.json"
    _write_supabase(path, workos=_WORKOS)
    enc_path = path.with_name(path.name + ".enc")
    enc_path.write_bytes(b"ciphertext")
    os.utime(path, (1000, 1000))
    os.utime(enc_path, (2000, 2000))

    monkeypatch.setattr(encrypted_storage, "is_supported", lambda: True)
    monkeypatch.setattr(encrypted_storage, "get_dek", lambda _dir: b"dek")

    def _boom(_p, _dek):
        raise ValueError("bad key")

    monkeypatch.setattr(encrypted_storage, "decrypt_file", _boom)

    tokens = credentials.load_credentials(path)
    assert tokens.access_token == "at-plain"  # fell back to plaintext


def _enc_only(tmp_path: Path, monkeypatch, workos: dict) -> Path:
    """Set up a Granola dir that ships only supabase.json.enc (no plaintext)."""
    path = tmp_path / "supabase.json"
    enc_path = path.with_name(path.name + ".enc")
    enc_path.write_bytes(b"ciphertext")

    monkeypatch.setattr(encrypted_storage, "is_supported", lambda: True)
    monkeypatch.setattr(encrypted_storage, "get_dek", lambda _dir: b"dek")
    monkeypatch.setattr(
        encrypted_storage,
        "decrypt_file",
        lambda _p, _dek: json.dumps({"workos_tokens": json.dumps(workos)}).encode(),
    )
    return path


def test_loads_when_only_enc_exists(tmp_path: Path, monkeypatch):
    path = _enc_only(tmp_path, monkeypatch, {**_WORKOS, "access_token": "at-enc"})
    assert credentials.load_credentials(path).access_token == "at-enc"


def test_save_keeps_tokens_encrypted_when_no_plaintext(tmp_path: Path, monkeypatch):
    path = _enc_only(tmp_path, monkeypatch, _WORKOS)
    monkeypatch.setattr(encrypted_storage, "encrypt_bytes", lambda data, _dek: b"new-ciphertext")

    credentials.save_workos_tokens(path, credentials.WorkOSTokens(**_WORKOS))

    assert not path.exists()  # never leak the tokens in the clear
    assert path.with_name(path.name + ".enc").read_bytes() == b"new-ciphertext"


def test_save_falls_back_to_plaintext_when_encryption_fails(tmp_path: Path, monkeypatch):
    path = _enc_only(tmp_path, monkeypatch, _WORKOS)

    def _boom(_data, _dek):
        raise ValueError("no key")

    monkeypatch.setattr(encrypted_storage, "encrypt_bytes", _boom)

    credentials.save_workos_tokens(path, credentials.WorkOSTokens(**_WORKOS))

    # Losing a rotated refresh token would break the next run, so plaintext wins here.
    saved = json.loads(json.loads(path.read_text(encoding="utf-8"))["workos_tokens"])
    assert saved["refresh_token"] == "rt-plain"


def test_decrypt_error_without_plaintext_raises(tmp_path: Path, monkeypatch):
    path = _enc_only(tmp_path, monkeypatch, _WORKOS)

    def _boom(_p, _dek):
        raise ValueError("bad key")

    monkeypatch.setattr(encrypted_storage, "decrypt_file", _boom)

    with pytest.raises(RuntimeError, match="Failed to decrypt"):
        credentials.load_credentials(path)
