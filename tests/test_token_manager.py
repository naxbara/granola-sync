"""Tests for token management (with mocked HTTP)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from granola_sync.auth.credentials import WorkOSTokens, load_credentials
from granola_sync.auth.token_manager import TokenManager


def _create_supabase_json(path: Path, obtained_at: int | None = None, expires_in: int = 21599) -> Path:
    """Create a mock supabase.json file."""
    if obtained_at is None:
        obtained_at = int(time.time() * 1000)

    tokens = {
        "access_token": "test-access-token-123",
        "expires_in": expires_in,
        "refresh_token": "test-refresh-token-abc",
        "token_type": "Bearer",
        "obtained_at": obtained_at,
        "session_id": "session_01test",
        "external_id": "ext-001",
        "sign_in_method": "GoogleOAuth",
    }

    supabase = {
        "workos_tokens": json.dumps(tokens),
        "cognito_tokens": json.dumps({
            "access_token": "cognito-token",
            "expires_in": 86400,
            "refresh_token": "cognito-refresh",
            "token_type": "Bearer",
            "obtained_at": obtained_at,
        }),
        "user_info": "{}",
    }

    file_path = path / "supabase.json"
    file_path.write_text(json.dumps(supabase, indent=2), encoding="utf-8")
    return file_path


def test_load_workos_tokens(tmp_path: Path):
    file_path = _create_supabase_json(tmp_path)
    tokens = load_credentials(file_path)

    assert isinstance(tokens, WorkOSTokens)
    assert tokens.access_token == "test-access-token-123"
    assert tokens.refresh_token == "test-refresh-token-abc"
    assert tokens.expires_in == 21599


def test_load_cognito_fallback(tmp_path: Path):
    """When workos_tokens is missing, fall back to cognito_tokens."""
    supabase = {
        "cognito_tokens": json.dumps({
            "access_token": "cognito-access",
            "expires_in": 86400,
            "refresh_token": "cognito-refresh",
            "token_type": "Bearer",
            "obtained_at": int(time.time() * 1000),
        }),
    }
    file_path = tmp_path / "supabase.json"
    file_path.write_text(json.dumps(supabase), encoding="utf-8")

    tokens = load_credentials(file_path)
    assert tokens.access_token == "cognito-access"


def test_load_no_tokens(tmp_path: Path):
    file_path = tmp_path / "supabase.json"
    file_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="No valid tokens"):
        load_credentials(file_path)


def test_token_manager_valid_token(tmp_path: Path):
    """A fresh token should be returned without refresh."""
    file_path = _create_supabase_json(tmp_path)
    tm = TokenManager(file_path, "client_test")

    assert tm.access_token == "test-access-token-123"


def test_token_manager_detects_expired(tmp_path: Path):
    """An old token should be detected as expired."""
    # Set obtained_at to 7 hours ago (token expires in ~6h)
    old_time = int((time.time() - 7 * 3600) * 1000)
    file_path = _create_supabase_json(tmp_path, obtained_at=old_time)

    tm = TokenManager(file_path, "client_test")
    assert tm._is_expired() is True


def test_token_manager_not_expired(tmp_path: Path):
    """A recent token should not be expired."""
    recent_time = int(time.time() * 1000)
    file_path = _create_supabase_json(tmp_path, obtained_at=recent_time)

    tm = TokenManager(file_path, "client_test")
    assert tm._is_expired() is False
