"""Snapshot-style tests for the .txt formatter — guards format stability."""

from __future__ import annotations

from datetime import UTC, datetime

from granola_sync.api.models import GranolaDocument, TranscriptUtterance
from granola_sync.exporter.txt_formatter import (
    format_document,
    generate_txt_filename,
)


def _doc(**overrides) -> GranolaDocument:
    defaults = dict(
        id="doc-1",
        title="Reunión de prueba",
        created_at=datetime(2026, 5, 8, 14, 30, tzinfo=UTC),
        updated_at=datetime(2026, 5, 8, 15, 30, tzinfo=UTC),
        google_calendar_event={
            "start": {"dateTime": "2026-05-08T14:30:00Z"},
            "end": {"dateTime": "2026-05-08T15:15:00Z"},
            "attendees": [
                {"email": "juan@example.com", "displayName": "Juan Pérez"},
                {"email": "maria@example.com", "displayName": "María González"},
            ],
        },
        people={
            "attendees": [
                {"name": "Juan Pérez", "email": "juan@example.com"},
                {"name": "María González", "email": "maria@example.com"},
            ]
        },
        last_viewed_panel={
            "document_id": "doc-1",
            "id": "panel-1",
            "content": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {"level": 1},
                        "content": [{"type": "text", "text": "Acuerdos"}],
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "Punto importante",
                                                "marks": [{"type": "bold"}],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                ],
            },
        },
    )
    defaults.update(overrides)
    return GranolaDocument(**defaults)


def test_format_document_includes_metadata_and_summary():
    out = format_document(_doc(), transcript=None)

    assert "Reunión de prueba" in out
    assert "Fecha: 8 de mayo de 2026" in out
    assert "Duración: 45 minutos" in out
    assert "Participantes: Juan Pérez, María González" in out
    assert "RESUMEN" in out
    # plain text — bold marker should be stripped
    assert "**Punto importante**" not in out
    assert "Punto importante" in out
    assert "Acuerdos" in out
    # transcript section omitted when None
    assert "TRANSCRIPCIÓN" not in out


def test_format_document_with_transcript():
    base_ts = datetime(2026, 5, 8, 14, 30, 0, tzinfo=UTC)
    utterances = [
        TranscriptUtterance(
            id="u1",
            document_id="doc-1",
            start_timestamp=base_ts,
            end_timestamp=base_ts,
            text="Hola, gracias por venir.",
            source="microphone",
        ),
        TranscriptUtterance(
            id="u2",
            document_id="doc-1",
            start_timestamp=base_ts.replace(second=12),
            end_timestamp=base_ts.replace(second=15),
            text="Encantada de estar aquí.",
            source="system",
        ),
    ]
    out = format_document(_doc(), transcript=utterances)

    assert "TRANSCRIPCIÓN" in out
    assert "[00:00:00] Tú: Hola, gracias por venir." in out
    assert "[00:00:12] Otro: Encantada de estar aquí." in out


def test_format_document_handles_missing_summary():
    doc = _doc(last_viewed_panel=None, notes=None, summary=None, overview=None)
    out = format_document(doc, transcript=None)
    assert "(Sin resumen disponible)" in out


def test_generate_txt_filename():
    assert generate_txt_filename("Reunión con Juan", "2026-05-08") == "2026-05-08 - reunion-con-juan.txt"
    assert generate_txt_filename("", "2026-05-08") == "2026-05-08 - reunion.txt"
