"""Read Granola credentials from the local supabase.json file.

The supabase.json file has a quirk: token fields (workos_tokens, cognito_tokens)
are stored as JSON *strings* inside the JSON file, requiring double parsing.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


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


def load_credentials(path: Path) -> WorkOSTokens:
    """Load and parse tokens from supabase.json.

    Tries WorkOS tokens first, falls back to Cognito tokens.

    Raises:
        FileNotFoundError: If supabase.json doesn't exist.
        ValueError: If no valid tokens are found.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))

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
        # Wrap in WorkOSTokens-compatible format
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
    corruption if the process crashes mid-write.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["workos_tokens"] = json.dumps(tokens.model_dump(), separators=(",", ":"))

    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    tmp_path.replace(path)
