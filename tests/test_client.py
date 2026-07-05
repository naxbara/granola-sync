"""Tests for the Granola API client (pagination, retries, 401 refresh)."""

from __future__ import annotations

import httpx
import pytest
import respx

from granola_sync.api import client as client_mod
from granola_sync.api.client import GranolaAPIClient


class _FakeTokenManager:
    def __init__(self) -> None:
        self.access_token = "tok"
        self.refresh_calls = 0

    def force_refresh(self) -> str:
        self.refresh_calls += 1
        self.access_token = "tok2"
        return self.access_token


def _doc(doc_id: str) -> dict:
    return {
        "id": doc_id,
        "title": f"Doc {doc_id}",
        "created_at": "2026-07-01T10:00:00Z",
        "updated_at": "2026-07-01T10:00:00Z",
    }


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)


@respx.mock
def test_get_documents_paginates():
    page1 = [_doc(str(i)) for i in range(100)]
    page2 = [_doc("100")]
    route = respx.post("https://api.granola.ai/v2/get-documents")
    route.side_effect = [
        httpx.Response(200, json={"docs": page1}),
        httpx.Response(200, json={"docs": page2}),
    ]

    api = GranolaAPIClient(_FakeTokenManager())
    docs = api.get_documents(limit=100)
    api.close()

    assert len(docs) == 101
    assert route.call_count == 2


@respx.mock
def test_retries_on_500_then_succeeds():
    route = respx.post("https://api.granola.ai/v2/get-documents")
    route.side_effect = [
        httpx.Response(500),
        httpx.Response(200, json={"docs": [_doc("1")]}),
    ]

    api = GranolaAPIClient(_FakeTokenManager())
    docs = api.get_documents()
    api.close()

    assert len(docs) == 1
    assert route.call_count == 2


@respx.mock
def test_401_forces_refresh_and_retries():
    route = respx.post("https://api.granola.ai/v1/get-document-transcript")
    route.side_effect = [
        httpx.Response(401),
        httpx.Response(200, json={"utterances": []}),
    ]

    tm = _FakeTokenManager()
    api = GranolaAPIClient(tm)
    api.get_transcript("doc-1")
    api.close()

    assert tm.refresh_calls == 1
    assert route.call_count == 2


@respx.mock
def test_raises_after_exhausting_retries():
    route = respx.post("https://api.granola.ai/v2/get-documents")
    route.side_effect = [httpx.Response(503) for _ in range(5)]

    api = GranolaAPIClient(_FakeTokenManager())
    with pytest.raises(httpx.HTTPStatusError):
        api.get_documents()
    api.close()
