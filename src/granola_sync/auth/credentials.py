"""Read Granola credentials from the local supabase.json (and .enc) file.

The supabase.json file has a quirk: token fields (workos_tokens, cognito_tokens)
are stored as JSON *strings* inside the JSON file, requiring double parsing.

Granola 2.x added an encrypted parallel file (supabase.json.enc). When present
and newer than the plaintext file, the desktop app treats it as the source of
truth. We mirror that behavior — read the encrypted file when newer, and write
both formats on save so the desktop app picks up our refreshed tokens.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel

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


def _enc_path(path: Path) -> Path:
    return path.with_name(path.name + ".enc")


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _read_raw(path: Path) -> dict:
    """Read the credential blob, preferring the encrypted file when newer."""
    enc_path = _enc_path(path)
    if (
        encrypted_storage.is_supported()
        and enc_path.exists()
        and _mtime(enc_path) > _mtime(path)
    ):
        try:
            dek = encrypted_storage.get_dek(path.parent)
            plaintext = encrypted_storage.decrypt_file(enc_path, dek)
            return json.loads(plaintext)
        except Exception as e:
            logger.warning("Failed to decrypt %s, falling back to plaintext: %s", enc_path, e)

    return json.loads(path.read_text(encoding="utf-8"))


def load_credentials(path: Path) -> WorkOSTokens:
    """Load and parse tokens from supabase.json (or supabase.json.enc).

    Tries WorkOS tokens first, falls back to Cognito tokens.

    Raises:
        FileNotFoundError: If supabase.json doesn't exist.
        ValueError: If no valid tokens are found.
    """
    raw = _read_raw(path)

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

    raise ValueError(f"No valid tokens found in {path}")


def save_workos_tokens(path: Path, tokens: WorkOSTokens) -> None:
    """Persist updated WorkOS tokens back to supabase.json atomically.

    Writes to a .tmp file first, then replaces the original to prevent
    corruption if the process crashes mid-write. When the encrypted variant
    exists, also rewrite it so the Granola desktop app reads our updates.
    """
    raw = _read_raw(path)
    raw["workos_tokens"] = json.dumps(tokens.model_dump(), separators=(",", ":"))

    plaintext_bytes = json.dumps(raw, indent=2).encode("utf-8")
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_bytes(plaintext_bytes)
    tmp_path.replace(path)

    enc_path = _enc_path(path)
    if encrypted_storage.is_supported() and enc_path.exists():
        try:
            dek = encrypted_storage.get_dek(path.parent)
            compact_bytes = json.dumps(raw, separators=(",", ":")).encode("utf-8")
            ciphertext = encrypted_storage.encrypt_bytes(compact_bytes, dek)
            enc_tmp = enc_path.with_suffix(enc_path.suffix + ".tmp")
            enc_tmp.write_bytes(ciphertext)
            enc_tmp.replace(enc_path)
        except Exception as e:
            logger.warning("Failed to update encrypted %s: %s", enc_path, e)
