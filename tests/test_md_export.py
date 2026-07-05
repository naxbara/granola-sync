"""Tests for the GUI's Obsidian-Markdown export path."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from granola_sync.api.models import GranolaDocument, TranscriptUtterance
from granola_sync.exporter.md_formatter import write_markdown_document


def _doc() -> GranolaDocument:
    return GranolaDocument(
        id="doc-1",
        title="Reunión de prueba",
        created_at=datetime(2026, 5, 8, 14, 30, tzinfo=UTC),
        updated_at=datetime(2026, 5, 8, 15, 30, tzinfo=UTC),
        last_viewed_panel={
            "document_id": "doc-1",
            "id": "p1",
            "content": {
                "type": "doc",
                "content": [
                    {"type": "heading", "attrs": {"level": 2},
                     "content": [{"type": "text", "text": "Acuerdos"}]},
                    {"type": "bulletList", "content": [
                        {"type": "listItem", "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "Punto uno"}]}]}]},
                ],
            },
        },
    )


def test_writes_md_with_frontmatter_and_markdown(tmp_path: Path):
    path = write_markdown_document(tmp_path, _doc(), None)
    assert path.suffix == ".md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "granola_id: doc-1" in text
    assert "## Acuerdos" in text     # markdown preserved (not stripped like .txt)
    assert "- Punto uno" in text


def test_md_includes_transcript_when_given(tmp_path: Path):
    uts = [
        TranscriptUtterance(
            id="u1", document_id="doc-1",
            start_timestamp=datetime(2026, 5, 8, 14, 30, tzinfo=UTC),
            end_timestamp=datetime(2026, 5, 8, 14, 30, tzinfo=UTC),
            text="Hola a todos", source="microphone",
        )
    ]
    text = write_markdown_document(tmp_path, _doc(), uts).read_text(encoding="utf-8")
    assert "Transcript:" in text
    assert "Hola a todos" in text
