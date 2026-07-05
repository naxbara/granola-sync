"""Tests for Claude enrichment (forced tool use, resilient to failures)."""

from __future__ import annotations

from types import SimpleNamespace

from granola_sync.enrichment.claude_enricher import ClaudeEnricher


class _FakeMessages:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return self._response


def _enricher_with(messages) -> ClaudeEnricher:
    enr = ClaudeEnricher(api_key="test-key")
    enr.client = SimpleNamespace(messages=messages)
    return enr


def test_enrich_returns_tool_input():
    tool_block = SimpleNamespace(
        type="tool_use",
        input={
            "projects": ["KYON"],
            "action_items": ["Enviar propuesta"],
            "tags": ["ventas"],
            "meeting_type": "sales",
            "follow_ups": [],
        },
    )
    messages = _FakeMessages(response=SimpleNamespace(content=[tool_block]))
    enr = _enricher_with(messages)

    result = enr.enrich("Reunión", "contenido con sustancia")
    assert result["meeting_type"] == "sales"
    assert result["projects"] == ["KYON"]
    # forced tool use was requested
    assert messages.calls[0]["tool_choice"]["name"] == "record_enrichment"


def test_enrich_empty_content_skips_api():
    messages = _FakeMessages(response=SimpleNamespace(content=[]))
    enr = _enricher_with(messages)
    assert enr.enrich("t", "   ") == {}
    assert messages.calls == []  # never called the API


def test_enrich_no_tool_block_returns_empty():
    text_block = SimpleNamespace(type="text", text="nope")
    messages = _FakeMessages(response=SimpleNamespace(content=[text_block]))
    enr = _enricher_with(messages)
    assert enr.enrich("t", "algo") == {}


def test_enrich_swallows_errors():
    messages = _FakeMessages(exc=RuntimeError("boom"))
    enr = _enricher_with(messages)
    assert enr.enrich("t", "algo") == {}
