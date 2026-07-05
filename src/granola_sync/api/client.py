"""Granola API client for the internal (reverse-engineered) endpoints."""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Any

import httpx

from .models import GranolaDocument, TranscriptUtterance

if TYPE_CHECKING:
    from ..auth.token_manager import TokenManager

logger = logging.getLogger(__name__)

BASE_URL = "https://api.granola.ai"
DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Granola/5.354.0",
    "X-Client-Version": "5.354.0",
}

# Transient HTTP statuses worth retrying with backoff.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_MAX_BACKOFF = 10.0
# get-documents-batch accepts many ids; chunk to keep requests reasonable.
_BATCH_CHUNK = 50


def _extract_doc_list(data: object) -> list[dict]:
    """Extract the document list from an API response.

    The API wraps results in different keys depending on the endpoint:
    - /v2/get-documents → {"docs": [...]} or list
    - /v1/get-documents-batch → {"docs": [...]} or list
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("docs", "documents"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


class GranolaAPIClient:
    """Client for the Granola internal API."""

    def __init__(self, token_manager: TokenManager) -> None:
        self._tm = token_manager
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers=DEFAULT_HEADERS,
            timeout=30.0,
            # Retry connection-level failures (DNS, connect, read resets).
            transport=httpx.HTTPTransport(retries=2),
        )

    def close(self) -> None:
        self._client.close()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._tm.access_token}"}

    def _post(self, path: str, payload: dict) -> Any:
        """POST with auth, retrying 429/5xx (backoff) and refreshing on 401.

        Raises httpx.HTTPStatusError / httpx.RequestError on final failure.
        """
        refreshed = False
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = self._client.post(path, json=payload, headers=self._auth_headers())
            except httpx.RequestError as e:
                if attempt < _MAX_ATTEMPTS - 1:
                    delay = self._backoff(attempt)
                    logger.warning("Network error on %s (%s), retrying in %.1fs", path, e, delay)
                    time.sleep(delay)
                    continue
                raise

            # A 401 despite our expiry estimate: force one refresh, then retry.
            if resp.status_code == 401 and not refreshed:
                refreshed = True
                logger.warning("401 from %s — forcing token refresh and retrying", path)
                self._tm.force_refresh()
                continue

            if resp.status_code in _RETRY_STATUSES and attempt < _MAX_ATTEMPTS - 1:
                delay = self._backoff(attempt)
                logger.warning(
                    "%s returned %d, retrying in %.1fs (attempt %d/%d)",
                    path, resp.status_code, delay, attempt + 1, _MAX_ATTEMPTS,
                )
                time.sleep(delay)
                continue

            resp.raise_for_status()
            return resp.json()

        # Attempts exhausted (e.g. repeated 401 or 5xx): surface the last response.
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(2 ** attempt + random.uniform(0, 0.5), _MAX_BACKOFF)

    def get_documents(self, limit: int = 100) -> list[GranolaDocument]:
        """Fetch all documents with auto-pagination."""
        all_docs: list[GranolaDocument] = []
        offset = 0

        while True:
            logger.debug("Fetching documents (offset=%d, limit=%d)", offset, limit)
            data = self._post(
                "/v2/get-documents",
                {
                    "limit": limit,
                    "offset": offset,
                    "include_last_viewed_panel": True,
                },
            )

            doc_list = _extract_doc_list(data)
            if not doc_list:
                break

            for raw_doc in doc_list:
                try:
                    all_docs.append(GranolaDocument(**raw_doc))
                except Exception as e:
                    doc_id = raw_doc.get("id", "unknown")
                    logger.warning("Failed to parse document %s: %s", doc_id, e)

            if len(doc_list) < limit:
                break
            offset += limit

        logger.info("Fetched %d documents from Granola", len(all_docs))
        return all_docs

    def get_transcript(self, document_id: str) -> list[TranscriptUtterance]:
        """Fetch transcript utterances for a document."""
        logger.debug("Fetching transcript for document %s", document_id)
        data = self._post("/v1/get-document-transcript", {"document_id": document_id})

        utterances_raw = data if isinstance(data, list) else data.get("utterances", [])
        utterances = []
        for raw in utterances_raw:
            try:
                utterances.append(TranscriptUtterance(**raw))
            except Exception as e:
                logger.warning("Failed to parse utterance: %s", e)

        return utterances

    def get_documents_batch(self, doc_ids: list[str]) -> list[GranolaDocument]:
        """Fetch multiple documents by ID (with full content including panels).

        Batches ids into chunks so a single call can hydrate many documents in
        one round-trip instead of one request per document.
        """
        docs: list[GranolaDocument] = []
        for start in range(0, len(doc_ids), _BATCH_CHUNK):
            chunk = doc_ids[start:start + _BATCH_CHUNK]
            data = self._post(
                "/v1/get-documents-batch",
                {"document_ids": chunk, "include_last_viewed_panel": True},
            )
            for d in _extract_doc_list(data):
                try:
                    docs.append(GranolaDocument(**d))
                except Exception as e:
                    logger.warning("Failed to parse batched document: %s", e)
        return docs
