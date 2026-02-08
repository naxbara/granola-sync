"""Tests for Obsidian template rendering."""

from datetime import datetime, timezone

from granola_sync.api.models import GranolaDocument, TranscriptUtterance
from granola_sync.converters.template import render_meeting_note


def _make_doc(**overrides) -> GranolaDocument:
    """Create a GranolaDocument with sensible defaults."""
    defaults = {
        "id": "test-doc-001",
        "title": "Test Meeting",
        "created_at": "2026-02-06T14:30:00Z",
        "updated_at": "2026-02-06T15:15:00Z",
    }
    defaults.update(overrides)
    return GranolaDocument(**defaults)


def _make_utterances() -> list[TranscriptUtterance]:
    """Create sample transcript utterances."""
    return [
        TranscriptUtterance(
            id="u1",
            document_id="test-doc-001",
            start_timestamp=datetime(2026, 2, 6, 14, 30, 0, tzinfo=timezone.utc),
            end_timestamp=datetime(2026, 2, 6, 14, 30, 10, tzinfo=timezone.utc),
            text="Hello everyone",
            source="system",
        ),
        TranscriptUtterance(
            id="u2",
            document_id="test-doc-001",
            start_timestamp=datetime(2026, 2, 6, 14, 30, 15, tzinfo=timezone.utc),
            end_timestamp=datetime(2026, 2, 6, 14, 30, 25, tzinfo=timezone.utc),
            text="Hi, thanks for joining",
            source="microphone",
        ),
    ]


def test_basic_rendering():
    doc = _make_doc()
    result = render_meeting_note(doc, "Some notes here")

    assert "---" in result
    assert "granola_id: test-doc-001" in result
    assert "type: meeting" in result
    assert "source: granola" in result
    assert "Some notes here" in result


def test_frontmatter_has_date():
    doc = _make_doc()
    result = render_meeting_note(doc, "")
    assert "date: '2026-02-06'" in result or "date: 2026-02-06" in result


def test_calendar_event_duration():
    doc = _make_doc(
        google_calendar_event={
            "start": {"dateTime": "2026-02-06T14:30:00-03:00"},
            "end": {"dateTime": "2026-02-06T15:15:00-03:00"},
        }
    )
    result = render_meeting_note(doc, "Notes")
    assert "45" in result  # 45 minutes duration


def test_participants():
    doc = _make_doc(
        people={
            "attendees": [
                {"email": "alice@example.com"},
                {"email": "bob@example.com"},
            ]
        }
    )
    result = render_meeting_note(doc, "Notes")
    assert "alice@example.com" in result
    assert "bob@example.com" in result


def test_with_summary_no_notes():
    doc = _make_doc(summary="This was a productive meeting about Q1 goals.")
    result = render_meeting_note(doc, "")
    assert "productive meeting" in result


def test_summary_not_shown_when_notes_present():
    doc = _make_doc(summary="Summary text")
    result = render_meeting_note(doc, "Actual notes content")
    assert "Actual notes content" in result
    assert "Summary text" not in result


def test_with_enrichment_in_frontmatter():
    doc = _make_doc()
    enrichment = {
        "projects": ["KYON XR"],
        "tags": ["sales", "q1"],
        "meeting_type": "sales",
    }
    result = render_meeting_note(doc, "Notes", enrichment=enrichment)

    assert "KYON XR" in result
    assert "meeting_type: sales" in result


def test_no_enrichment():
    doc = _make_doc()
    result = render_meeting_note(doc, "Notes")
    assert "## Action Items" not in result
    assert "## Follow-ups" not in result


def test_with_transcript_embedded():
    doc = _make_doc()
    utterances = _make_utterances()
    result = render_meeting_note(doc, "Notes", utterances=utterances)

    assert "Transcript:" in result
    assert "**[14:30:00]** _Speaker_: Hello everyone" in result
    assert "**[14:30:15]** _You_: Hi, thanks for joining" in result


def test_meeting_metadata_section():
    doc = _make_doc(
        people={
            "attendees": [
                {"email": "alice@example.com"},
            ]
        }
    )
    result = render_meeting_note(doc, "Notes")

    assert "Meeting Title: Test Meeting" in result
    assert "Date: 2026-02-06" in result
    assert "Meeting participants: alice@example.com" in result
    assert "notes.granola.ai/t/test-doc-001" in result


def test_no_old_format_sections():
    """Verify old format sections are gone."""
    doc = _make_doc(summary="Some summary")
    result = render_meeting_note(doc, "Notes")

    assert "## Summary" not in result
    assert "## Notes" not in result
    assert "> [!info] Context" not in result
    assert "## References" not in result
    assert "## Action Items" not in result
    assert "## Follow-ups" not in result
