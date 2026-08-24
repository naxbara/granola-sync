"""Tests for matching a Granola meeting to its Google Calendar event.

The rule these enforce: when the match is not clear, return nothing. A wrong
roster on a note is worse than an empty one, because it reads as fact.
"""

from datetime import UTC, datetime

from granola_sync.sources.calendar import CalendarLookup


class _FakeEvents:
    def __init__(self, items):
        self._items = items
        self.calls = 0

    def list(self, **kwargs):
        self.calls += 1
        return self

    def execute(self):
        return {"items": self._items}


class _FakeService:
    def __init__(self, items):
        self._events = _FakeEvents(items)

    def events(self):
        return self._events


def _event(summary, hour, minute=0, attendees=None, all_day=False):
    if all_day:
        start = {"date": "2026-08-21"}
    else:
        start = {"dateTime": f"2026-08-21T{hour:02d}:{minute:02d}:00+00:00"}
    return {
        "summary": summary,
        "start": start,
        "attendees": [{"email": e} for e in (attendees or [])],
    }


def _lookup(items, **kwargs):
    return CalendarLookup(_FakeService(items), **kwargs)


def _at(hour, minute=0):
    return datetime(2026, 8, 21, hour, minute, tzinfo=UTC)


def test_matches_by_title_and_time():
    lookup = _lookup([_event("Levantamiento Procesos", 8, 30, ["a@vc.com", "b@catchai.ai"])])
    assert lookup.emails_for("Levantamiento Procesos", _at(8, 35)) == [
        "a@vc.com",
        "b@catchai.ai",
    ]


def test_addresses_are_normalized():
    lookup = _lookup([_event("Daily", 9, 0, ["Ana@Habitat.CL"])])
    assert lookup.emails_for("Daily", _at(9)) == ["ana@habitat.cl"]


def test_a_meeting_outside_the_window_does_not_match():
    lookup = _lookup([_event("Daily", 9, 0, ["a@x.cl"])])
    assert lookup.emails_for("Daily", _at(14)) == []


def test_an_unrelated_title_does_not_match():
    lookup = _lookup([_event("Almuerzo con Rodrigo", 9, 0, ["a@x.cl"])])
    assert lookup.emails_for("Revisión de arquitectura Hábitat", _at(9)) == []


def test_two_similar_events_at_once_are_left_alone():
    """Back-to-back recurring meetings are exactly where a guess goes wrong."""
    lookup = _lookup(
        [
            _event("Reunion Diaria Catchai", 9, 0, ["a@catchai.ai"]),
            _event("Reunion Diaria Catchai", 9, 15, ["b@catchai.ai"]),
        ]
    )
    assert lookup.emails_for("Reunion Diaria Catchai", _at(9, 5)) == []


def test_a_loosely_named_event_still_matches():
    """Real case: the meeting and the invite name the client differently.

    'Geovita presentación' vs 'Geovitas y Sebastián Suárez' scores 59 — above
    the 55 default, and far above the 38 of the nearest wrong candidate.
    """
    lookup = _lookup([_event("Geovitas  y Sebastián Suárez", 11, 0, ["a@geovita.cl"])])
    assert lookup.emails_for("Geovita presentación", _at(11, 14)) == ["a@geovita.cl"]


def test_a_different_meeting_at_the_same_hour_is_refused():
    """Real case: 'Abastible' had a 7-person event 7 minutes away.

    Taking it would have stamped seven strangers onto the note.
    """
    lookup = _lookup(
        [_event("Un café con Rodrigo & Crosslines", 16, 0, ["r@x.cl", "c@y.cl"])]
    )
    assert lookup.emails_for("Abastible", _at(16, 7)) == []


def test_all_day_events_are_ignored():
    lookup = _lookup([_event("Cumpleaños", 0, all_day=True, attendees=["a@x.cl"])])
    assert lookup.emails_for("Cumpleaños", _at(9)) == []


def test_a_matched_event_without_attendees_yields_nothing():
    """A personal block matches by name but has nobody in it."""
    lookup = _lookup([_event("Marshall talk", 15, 0, [])])
    assert lookup.emails_for("Marshall talk", _at(15)) == []


def test_meeting_rooms_are_not_people():
    lookup = _lookup(
        [
            {
                "summary": "Comité",
                "start": {"dateTime": "2026-08-21T09:00:00+00:00"},
                "attendees": [
                    {"email": "sala@resource.calendar.google.com", "resource": True},
                    {"email": "ana@x.cl"},
                ],
            }
        ]
    )
    assert lookup.emails_for("Comité", _at(9)) == ["ana@x.cl"]


def test_a_naive_timestamp_is_refused():
    """Without a timezone we cannot compare against the calendar honestly."""
    lookup = _lookup([_event("Daily", 9, 0, ["a@x.cl"])])
    assert lookup.emails_for("Daily", datetime(2026, 8, 21, 9, 0)) == []


def test_events_are_fetched_once_per_day():
    lookup = _lookup([_event("Daily", 9, 0, ["a@x.cl"])])
    lookup.emails_for("Daily", _at(9))
    lookup.emails_for("Daily", _at(9, 10))
    assert lookup._service.events().calls == 1


def test_a_calendar_failure_is_not_fatal():
    class _Broken:
        def events(self):
            raise RuntimeError("network down")

    lookup = CalendarLookup(_Broken())
    assert lookup.emails_for("Daily", _at(9)) == []
