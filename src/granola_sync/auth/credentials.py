"""Read Granola credentials from the app's local storage.

Two layouts exist:

* stored-accounts.json (Granola 7.8+, multi-account). The app migrates the
  session out of supabase.json on first launch and leaves supabase.json empty:
  ``{"version": 2, "currentUserId": "<id>",
  "accountsById": {"<id>": {"user": {...}, "tokens": {<WorkOS tokens>}, ...}}}``.
  Once it carries a ``version``, this file is the source of truth.

* supabase.json (older builds). Token fields (workos_tokens, cognito_tokens)
  are stored as JSON *strings* inside the JSON file, requiring double parsing.

Granola 2.x added encrypted parallel files (*.json.enc). When present and newer
than the plaintext file, the desktop app treats them as the source of truth. We
mirror that behavior — read the encrypted file when newer, and write both
formats on save so the desktop app picks up our refreshed tokens.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel

from ..utils import encrypted_credentials_path
from . import encrypted_storage

logger = logging.getLogger(__name__)


class WorkOSTokens(BaseModel):
    """WorkOS authentication tokens (primary)."""

    access_token: str
    expires_in: int  # seconds, typically ~21600 (~6h)
    refresh_token: str
    token_type: str = "Bearer"
    obtained_at: int = 0  # epoch milliseconds
    session_id: str | None = None
    external_id: str | None = None
    sign_in_method: str | None = None


class CognitoTokens(BaseModel):
    """Cognito authentication tokens (fallback)."""

    access_token: str
    expires_in: int  # seconds, typically 86400 (24h)
    refresh_token: str
    token_type: str = "Bearer"
    id_token: str | None = None
    obtained_at: int = 0


class NoTokensError(ValueError):
    """The credential file was read but holds no session tokens.

    Happens when the Granola app is signed out, or caught mid-rewrite of its
    credential file (it rewrites it on sign-in and on session refresh).
    """

    def __init__(self, source: Path) -> None:
        self.source = source
        super().__init__(
            f"No valid tokens found in {source}. The Granola app has no active "
            "session right now: open Granola, make sure you are signed in, and "
            "run the sync again. If you just signed in, wait a few seconds first."
        )


def _enc_path(path: Path) -> Path:
    return encrypted_credentials_path(path)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _read_raw_with_source(path: Path) -> tuple[dict, Path]:
    """Read the credential blob and say which file it came from.

    Prefers the encrypted file when newer, mirroring the desktop app.
    """
    enc_path = _enc_path(path)
    if (
        encrypted_storage.is_supported()
        and enc_path.exists()
        and _mtime(enc_path) > _mtime(path)
    ):
        try:
            dek = encrypted_storage.get_dek(path.parent)
            plaintext = encrypted_storage.decrypt_file(enc_path, dek)
            return json.loads(plaintext), enc_path
        except Exception as e:
            # Recent Granola builds ship no plaintext twin, so there is nothing
            # to fall back to — surface the decryption failure instead.
            if not path.exists():
                raise RuntimeError(f"Failed to decrypt {enc_path}: {e}") from e
            logger.warning("Failed to decrypt %s, falling back to plaintext: %s", enc_path, e)

    return json.loads(path.read_text(encoding="utf-8")), path


def _read_raw(path: Path) -> dict:
    """Read the credential blob, preferring the encrypted file when newer."""
    return _read_raw_with_source(path)[0]


STORED_ACCOUNTS_FILE = "stored-accounts.json"


def stored_accounts_path(path: Path) -> Path:
    """Return the stored-accounts.json that sits next to a supabase.json path."""
    return path.with_name(STORED_ACCOUNTS_FILE)


def _maybe_json(value):
    """Decode a value the app may have stored as a JSON string."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _read_stored_accounts(path: Path) -> tuple[dict, Path] | None:
    """Read stored-accounts.json(.enc) when it is the app's source of truth.

    Returns None when the file is missing or not migrated yet (no ``version``),
    so the caller falls back to supabase.json.
    """
    accounts_path = stored_accounts_path(path)
    if not (accounts_path.exists() or _enc_path(accounts_path).exists()):
        return None
    raw, source = _read_raw_with_source(accounts_path)
    if not isinstance(raw, dict) or raw.get("version") is None:
        return None
    return raw, source


def _current_account(raw: dict) -> dict | None:
    """Return the signed-in account entry of a stored-accounts blob."""
    accounts = _maybe_json(raw.get("accountsById")) or {}
    user_id = _maybe_json(raw.get("currentUserId"))
    if not isinstance(accounts, dict) or not user_id:
        return None
    account = accounts.get(user_id)
    return account if isinstance(account, dict) else None


def load_credentials(path: Path) -> WorkOSTokens:
    """Load and parse the signed-in session's tokens.

    Reads stored-accounts.json(.enc) when Granola already migrated to it;
    otherwise supabase.json(.enc), where WorkOS tokens are tried first and
    Cognito tokens are the fallback.

    Raises:
        FileNotFoundError: If no credential file exists.
        NoTokensError: If no valid tokens are found (a ValueError).
    """
    stored = _read_stored_accounts(path)
    if stored is not None:
        raw, source = stored
        account = _current_account(raw)
        tokens = _maybe_json(account.get("tokens")) if account else None
        if isinstance(tokens, dict) and tokens.get("access_token"):
            return WorkOSTokens(**tokens)
        raise NoTokensError(source)

    raw, source = _read_raw_with_source(path)

    # workos_tokens is stored as a JSON string within the JSON
    workos_str = raw.get("workos_tokens")
    if workos_str:
        workos_data = json.loads(workos_str) if isinstance(workos_str, str) else workos_str
        return WorkOSTokens(**workos_data)

    # Fallback: cognito_tokens
    cognito_str = raw.get("cognito_tokens")
    if cognito_str:
        cognito_data = json.loads(cognito_str) if isinstance(cognito_str, str) else cognito_str
        cog = CognitoTokens(**cognito_data)
        return WorkOSTokens(
            access_token=cog.access_token,
            expires_in=cog.expires_in,
            refresh_token=cog.refresh_token,
            token_type=cog.token_type,
            obtained_at=cog.obtained_at,
        )

    raise NoTokensError(source)


def save_workos_tokens(path: Path, tokens: WorkOSTokens) -> None:
    """Persist updated WorkOS tokens back to Granola's storage atomically.

    Writes to stored-accounts.json(.enc) when Granola already migrated to it
    (updating only the signed-in account's tokens), else to supabase.json(.enc).
    """
    stored = _read_stored_accounts(path)
    if stored is not None:
        raw, source = stored
        account = _current_account(raw)
        if account is None:
            raise NoTokensError(source)
        old_tokens = account.get("tokens")
        # Keep any token fields the app stores that our model does not know.
        merged = {**(_maybe_json(old_tokens) or {}), **tokens.model_dump(exclude_none=True)}
        account["tokens"] = (
            json.dumps(merged, separators=(",", ":")) if isinstance(old_tokens, str) else merged
        )
        accounts = _maybe_json(raw.get("accountsById"))
        accounts[_maybe_json(raw.get("currentUserId"))] = account
        if isinstance(raw.get("accountsById"), str):
            raw["accountsById"] = json.dumps(accounts, separators=(",", ":"))
        else:
            raw["accountsById"] = accounts
        _write_blob(stored_accounts_path(path), raw)
        return

    raw = _read_raw(path)
    raw["workos_tokens"] = json.dumps(tokens.model_dump(), separators=(",", ":"))
    _write_blob(path, raw)


def _write_blob(path: Path, raw: dict) -> None:
    """Write a credential blob to ``path`` and its encrypted twin.

    Writes to a .tmp file first, then replaces the original to prevent
    corruption if the process crashes mid-write. When the encrypted variant
    exists, also rewrite it so the Granola desktop app reads our updates.
    """

    def write_plaintext() -> None:
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_bytes(json.dumps(raw, indent=2).encode("utf-8"))
        tmp_path.replace(path)

    # Only refresh the plaintext file when Granola still keeps one — creating it
    # from scratch would leave the tokens on disk in the clear.
    if path.exists():
        write_plaintext()

    enc_path = _enc_path(path)
    encrypted = False
    if encrypted_storage.is_supported() and enc_path.exists():
        try:
            dek = encrypted_storage.get_dek(path.parent)
            compact_bytes = json.dumps(raw, separators=(",", ":")).encode("utf-8")
            ciphertext = encrypted_storage.encrypt_bytes(compact_bytes, dek)
            enc_tmp = enc_path.with_suffix(enc_path.suffix + ".tmp")
            enc_tmp.write_bytes(ciphertext)
            enc_tmp.replace(enc_path)
            encrypted = True
        except Exception as e:
            logger.warning("Failed to update encrypted %s: %s", enc_path, e)

    if not encrypted and not path.exists():
        # Nothing persisted the rotated refresh token; plaintext is the last resort.
        logger.warning("Falling back to plaintext credentials at %s", path)
        write_plaintext()
