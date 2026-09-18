"""Meeting dates and transcript times are rendered in local time, not UTC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from granola_sync import utils
from granola_sync.api.models import GranolaDocument, TranscriptUtterance
from granola_sync.converters.template import render_meeting_note
from granola_sync.converters.transcript import render_utterances

SANTIAGO_SUMMER = timezone(timedelta(hours=-3))


@pytest.fixture(autouse=True)
def _santiago(monkeypatch):
    monkeypatch.setattr(utils, "LOCAL_TZ", SANTIAGO_SUMMER)


def _doc(**overrides) -> GranolaDocument:
    data = {
        "id": "d1",
        "title": "Revisión flujo Operaciones",
        "created_at": "2026-09-16T19:02:00Z",
        "updated_at": "2026-09-16T20:10:00Z",
    }
    data.update(overrides)
    return GranolaDocument(**data)


def test_created_at_in_utc_is_shown_in_local_time():
    note = render_meeting_note(_doc(), "Notas")
    assert "date: '2026-09-16'" in note
    assert "time: '16:02'" in note


def test_calendar_start_in_utc_is_shown_in_local_time():
    # Granola stores calendar starts in UTC too ("...Z"), not in the event's zone.
    doc = _doc(
        google_calendar_event={
            "start": {"dateTime": "2026-09-16T19:00:00Z"},
            "end": {"dateTime": "2026-09-16T20:00:00Z"},
        }
    )
    note = render_meeting_note(doc, "Notas")
    assert "time: '16:00'" in note
    assert "duration: 60min" in note


def test_evening_meeting_keeps_its_local_day():
    # 22:30 in Santiago is 01:30 UTC of the next day.
    doc = _doc(created_at="2026-09-17T01:30:00Z")
    assert doc.meeting_date.strftime("%Y-%m-%d %H:%M") == "2026-09-16 22:30"


def test_transcript_timestamps_are_local():
    u = TranscriptUtterance(
        id="u1",
        document_id="d1",
        start_timestamp=datetime(2026, 9, 16, 19, 0, 5, tzinfo=UTC),
        end_timestamp=datetime(2026, 9, 16, 19, 0, 9, tzinfo=UTC),
        text="Hola",
        source="microphone",
    )
    assert "**[16:00:05]** _You_: Hola" in render_utterances([u])
