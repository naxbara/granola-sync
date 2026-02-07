"""WorkOS token management with single-use refresh token rotation.

Key behaviors:
- Access tokens expire in ~6 hours.
- Refresh tokens are SINGLE-USE: once exchanged, the old one is invalidated.
- The Granola desktop app also refreshes tokens, so we must re-read the file
  before attempting a refresh to avoid using an already-rotated token.
- New tokens must be persisted atomically before being used.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import httpx

from .credentials import WorkOSTokens, load_credentials, save_workos_tokens

logger = logging.getLogger(__name__)

WORKOS_AUTH_URL = "https://api.workos.com/user_management/authenticate"
EXPIRY_BUFFER_MS = 300_000  # 5 minutes before actual expiry


class TokenManager:
    """Thread-safe WorkOS token manager with automatic refresh."""

    def __init__(self, credentials_path: Path, client_id: str) -> None:
        self._creds_path = credentials_path
        self._client_id = client_id
        self._tokens = load_credentials(credentials_path)
        self._lock = threading.Lock()

    @property
    def access_token(self) -> str:
        """Get a valid access token, refreshing if expired."""
        if self._is_expired():
            self._ensure_valid_token()
        return self._tokens.access_token

    def _is_expired(self) -> bool:
        """Check if the current access token has expired (with 5-min buffer)."""
        if self._tokens.obtained_at == 0:
            return False  # No timestamp, assume valid
        elapsed_ms = (time.time() * 1000) - self._tokens.obtained_at
        expires_ms = self._tokens.expires_in * 1000
        return elapsed_ms >= (expires_ms - EXPIRY_BUFFER_MS)

    def _ensure_valid_token(self) -> None:
        """Get a valid token, handling Granola app conflicts."""
        with self._lock:
            # Re-check after acquiring lock
            if not self._is_expired():
                return

            # Step 1: Re-read file — Granola app may have refreshed already
            fresh_tokens = load_credentials(self._creds_path)
            if fresh_tokens.obtained_at > self._tokens.obtained_at:
                self._tokens = fresh_tokens
                if not self._is_expired():
                    logger.debug("Using tokens refreshed by Granola app")
                    return

            # Step 2: Refresh ourselves
            try:
                self._refresh()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    # Refresh token was already used by Granola app — re-read one more time
                    logger.warning("Refresh token rejected (already rotated), re-reading file")
                    self._tokens = load_credentials(self._creds_path)
                    if not self._is_expired():
                        return
                    raise RuntimeError(
                        "Token refresh failed and no valid token in supabase.json. "
                        "Try opening the Granola app to generate fresh tokens."
                    ) from e
                raise

    def _refresh(self) -> None:
        """Exchange refresh token for a new access + refresh token pair."""
        logger.info("Refreshing WorkOS access token...")

        response = httpx.post(
            WORKOS_AUTH_URL,
            json={
                "client_id": self._client_id,
                "grant_type": "refresh_token",
                "refresh_token": self._tokens.refresh_token,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()

        new_tokens = WorkOSTokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=data.get("expires_in", 21599),
            token_type=data.get("token_type", "Bearer"),
            obtained_at=int(time.time() * 1000),
            session_id=self._tokens.session_id,
            external_id=self._tokens.external_id,
            sign_in_method=self._tokens.sign_in_method,
        )

        # PERSIST IMMEDIATELY before anything else
        save_workos_tokens(self._creds_path, new_tokens)
        self._tokens = new_tokens
        logger.info("Token refreshed and persisted successfully")
