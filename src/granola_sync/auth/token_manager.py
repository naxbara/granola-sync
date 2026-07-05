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

        if self._tokens.obtained_at == 0:
            # No timestamp (e.g. Cognito fallback tokens) — we can't predict
            # expiry, so we optimistically use the token and rely on a 401 from
            # the API to trigger force_refresh() rather than refreshing blindly.
            logger.warning(
                "Loaded tokens without an obtained_at timestamp; expiry cannot be "
                "predicted. Will refresh on a 401 from the API."
            )

    @property
    def access_token(self) -> str:
        """Get a valid access token, refreshing if expired."""
        if self._is_expired():
            self._ensure_valid_token()
        return self._tokens.access_token

    def force_refresh(self) -> str:
        """Force a token refresh regardless of the local clock.

        Called when the API returns 401 despite our expiry estimate saying the
        token is still valid (e.g. the token was revoked server-side, or the
        Granola app rotated it out from under us).
        """
        with self._lock:
            prev_obtained = self._tokens.obtained_at

            # The Granola desktop app may have already rotated the token —
            # prefer the file if it holds newer tokens than ours.
            fresh = load_credentials(self._creds_path)
            if fresh.obtained_at > prev_obtained:
                self._tokens = fresh
                logger.debug("force_refresh: using tokens rotated by Granola app")
                return self._tokens.access_token

            try:
                self._refresh()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (400, 401):
                    self._tokens = load_credentials(self._creds_path)
                    if self._tokens.obtained_at > prev_obtained:
                        return self._tokens.access_token
                    raise RuntimeError(
                        "WorkOS rejected the refresh token (likely expired or already "
                        "rotated). Open the Granola desktop app to re-authenticate, then "
                        f"retry. WorkOS response: {e.response.text}"
                    ) from e
                raise

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
                # WorkOS returns 400 (invalid_grant) or 401 when the refresh token
                # has been rotated/invalidated. Treat both the same way.
                if e.response.status_code in (400, 401):
                    body = e.response.text
                    logger.warning(
                        "Refresh token rejected (status %s): %s. Re-reading file in case Granola rotated it.",
                        e.response.status_code,
                        body,
                    )
                    self._tokens = load_credentials(self._creds_path)
                    if not self._is_expired():
                        return
                    raise RuntimeError(
                        "WorkOS rejected the refresh token (likely expired or already rotated). "
                        "Open the Granola desktop app to re-authenticate, then retry. "
                        f"WorkOS response: {body}"
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
