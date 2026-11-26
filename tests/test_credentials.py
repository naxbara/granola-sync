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


def test_signed_out_enc_names_the_enc_file(tmp_path: Path, monkeypatch):
    # Granola signed out (or mid-rewrite): the .enc decrypts but carries no tokens.
    path = _enc_only(tmp_path, monkeypatch, _WORKOS)
    monkeypatch.setattr(
        encrypted_storage,
        "decrypt_file",
        lambda _p, _dek: json.dumps({"session_id": "s"}).encode(),
    )

    with pytest.raises(credentials.NoTokensError) as excinfo:
        credentials.load_credentials(path)

    enc_path = path.with_name(path.name + ".enc")
    assert excinfo.value.source == enc_path
    assert str(enc_path) in str(excinfo.value)
    assert "signed in" in str(excinfo.value)
    assert isinstance(excinfo.value, ValueError)  # older callers catch ValueError


# --- Granola 7.8+: stored-accounts.json(.enc) -------------------------------

_USER_ID = "user-1"


def _stored_accounts_blob(tokens: dict | None, current: str | None = _USER_ID) -> dict:
    accounts = {}
    if tokens is not None:
        accounts[_USER_ID] = {
            "user": {"id": _USER_ID, "email": "owner@example.com"},
            "tokens": tokens,
            "savedAt": 1,
            "workspaces": [],
        }
    return {"version": 2, "currentUserId": current, "accountsById": accounts}


def _migrated(tmp_path: Path, monkeypatch, blob: dict) -> tuple[Path, dict]:
    """Granola dir after the 7.8 migration: emptied supabase.json.enc plus stored-accounts.

    Returns the supabase.json path and a dict that records encrypted writes per file.
    """
    path = tmp_path / "supabase.json"
    path.with_name("supabase.json.enc").write_bytes(b"empty")
    path.with_name("stored-accounts.json.enc").write_bytes(b"accounts")
    files = {
        "supabase.json.enc": json.dumps({}),  # the app clears it after migrating
        "stored-accounts.json.enc": json.dumps(blob),
    }
    writes: dict = {}

    monkeypatch.setattr(encrypted_storage, "is_supported", lambda: True)
    monkeypatch.setattr(encrypted_storage, "get_dek", lambda _dir: b"dek")
    monkeypatch.setattr(
        encrypted_storage, "decrypt_file", lambda p, _dek: files[Path(p).name].encode()
    )
    monkeypatch.setattr(encrypted_storage, "encrypt_bytes", lambda data, _dek: b"ENC:" + data)
    return path, writes


def test_loads_current_account_from_stored_accounts(tmp_path: Path, monkeypatch):
    path, _ = _migrated(tmp_path, monkeypatch, _stored_accounts_blob({**_WORKOS, "access_token": "at-acc"}))
    assert credentials.load_credentials(path).access_token == "at-acc"


def test_stored_accounts_tokens_as_json_string(tmp_path: Path, monkeypatch):
    blob = _stored_accounts_blob(None)
    blob["accountsById"] = json.dumps(
        {_USER_ID: {"user": {"id": _USER_ID}, "tokens": json.dumps({**_WORKOS, "access_token": "at-str"})}}
    )
    path, _ = _migrated(tmp_path, monkeypatch, blob)
    assert credentials.load_credentials(path).access_token == "at-str"


def test_stored_accounts_signed_out_names_that_file(tmp_path: Path, monkeypatch):
    path, _ = _migrated(tmp_path, monkeypatch, _stored_accounts_blob(_WORKOS, current=None))
    with pytest.raises(credentials.NoTokensError) as excinfo:
        credentials.load_credentials(path)
    assert excinfo.value.source == path.with_name("stored-accounts.json.enc")


def test_unmigrated_stored_accounts_falls_back_to_supabase(tmp_path: Path, monkeypatch):
    # Before the migration finishes there is no "version": supabase.json still rules.
    path = _enc_only(tmp_path, monkeypatch, {**_WORKOS, "access_token": "at-legacy"})
    path.with_name("stored-accounts.json").write_text(json.dumps({"accounts": "[]"}), encoding="utf-8")
    assert credentials.load_credentials(path).access_token == "at-legacy"


def test_save_updates_current_account_in_stored_accounts(tmp_path: Path, monkeypatch):
    old = {**_WORKOS, "session_id": "sess", "extra_field": "keep-me"}
    path, _ = _migrated(tmp_path, monkeypatch, _stored_accounts_blob(old))

    new = credentials.WorkOSTokens(**{**_WORKOS, "access_token": "at-new", "refresh_token": "rt-new"})
    credentials.save_workos_tokens(path, new)

    accounts_enc = path.with_name("stored-accounts.json.enc").read_bytes()
    assert accounts_enc.startswith(b"ENC:")
    saved = json.loads(accounts_enc[len(b"ENC:"):])
    tokens = saved["accountsById"][_USER_ID]["tokens"]
    assert tokens["access_token"] == "at-new"
    assert tokens["refresh_token"] == "rt-new"
    assert tokens["extra_field"] == "keep-me"  # unknown fields survive
    assert saved["accountsById"][_USER_ID]["user"]["email"] == "owner@example.com"
    assert saved["currentUserId"] == _USER_ID and saved["version"] == 2
    # Never touch the legacy file nor leak tokens in the clear.
    assert path.with_name("supabase.json.enc").read_bytes() == b"empty"
    assert not path.exists()
    assert not path.with_name("stored-accounts.json").exists()


def test_credentials_exist_sees_stored_accounts(tmp_path: Path):
    from granola_sync.utils import credentials_exist

    path = tmp_path / "supabase.json"
    assert not credentials_exist(path)
    path.with_name("stored-accounts.json.enc").write_bytes(b"x")
    assert credentials_exist(path)
