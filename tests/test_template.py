"""Tests for Obsidian template rendering."""

from granola_sync.api.models import GranolaDocument
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


def test_basic_rendering():
    doc = _make_doc()
    result = render_meeting_note(doc, "Some notes here")

    assert "---" in result
    assert "granola_id: test-doc-001" in result
    assert "type: meeting" in result
    assert "source: granola" in result
    assert "# Test Meeting" in result
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


def test_with_summary():
    doc = _make_doc(summary="This was a productive meeting about Q1 goals.")
    result = render_meeting_note(doc, "Notes")
    assert "## Summary" in result
    assert "productive meeting" in result


def test_with_enrichment():
    doc = _make_doc()
    enrichment = {
        "projects": ["KYON XR"],
        "action_items": ["Send proposal", "Schedule follow-up"],
        "tags": ["sales", "q1"],
        "meeting_type": "sales",
        "follow_ups": ["Review budget next week"],
    }
    result = render_meeting_note(doc, "Notes", enrichment=enrichment)

    assert "## Action Items" in result
    assert "- [ ] Send proposal #todo" in result
    assert "- [ ] Schedule follow-up #todo" in result
    assert "## Follow-ups" in result
    assert "Review budget next week" in result
    assert "KYON XR" in result
    assert "meeting_type: sales" in result


def test_with_transcript_link():
    doc = _make_doc()
    result = render_meeting_note(
        doc, "Notes", transcript_filename="2026-02-06-test-meeting-transcript.md"
    )
    assert "## References" in result
    assert "[[2026-02-06-test-meeting-transcript|Full transcript]]" in result


def test_no_enrichment():
    doc = _make_doc()
    result = render_meeting_note(doc, "Notes")
    assert "## Action Items" not in result
    assert "## Follow-ups" not in result
