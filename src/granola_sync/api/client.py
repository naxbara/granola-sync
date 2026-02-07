"""Granola API client for the internal (reverse-engineered) endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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


class GranolaAPIClient:
    """Client for the Granola internal API."""

    def __init__(self, token_manager: TokenManager) -> None:
        self._tm = token_manager
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers=DEFAULT_HEADERS,
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._tm.access_token}"}

    def get_documents(self, limit: int = 100) -> list[GranolaDocument]:
        """Fetch all documents with auto-pagination."""
        all_docs: list[GranolaDocument] = []
        offset = 0

        while True:
            logger.debug("Fetching documents (offset=%d, limit=%d)", offset, limit)
            resp = self._client.post(
                "/v2/get-documents",
                json={
                    "limit": limit,
                    "offset": offset,
                    "include_last_viewed_panel": True,
                },
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

            # Response can be a list or wrapped in an object
            doc_list = data if isinstance(data, list) else data.get("documents", data.get("docs", []))
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
        resp = self._client.post(
            "/v1/get-document-transcript",
            json={"document_id": document_id},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

        utterances_raw = data if isinstance(data, list) else data.get("utterances", [])
        utterances = []
        for raw in utterances_raw:
            try:
                utterances.append(TranscriptUtterance(**raw))
            except Exception as e:
                logger.warning("Failed to parse utterance: %s", e)

        return utterances

    def get_documents_batch(self, doc_ids: list[str]) -> list[GranolaDocument]:
        """Fetch multiple documents by ID."""
        resp = self._client.post(
            "/v1/get-documents-batch",
            json={
                "document_ids": doc_ids,
                "include_last_viewed_panel": True,
            },
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        doc_list = data if isinstance(data, list) else data.get("documents", [])
        return [GranolaDocument(**d) for d in doc_list]
