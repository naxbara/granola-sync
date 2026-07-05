"""Tests for explicit date-range filtering in the exporter."""

from __future__ import annotations

from datetime import date

from granola_sync.api.models import GranolaDocument
from granola_sync.exporter.runner import _filter_docs


def _d(doc_id: str, iso: str) -> GranolaDocument:
    # Midday UTC so the local calendar date matches the UTC date in any tz.
    return GranolaDocument(id=doc_id, title=doc_id, created_at=iso, updated_at=iso)


DOCS = [
    _d("a", "2026-07-01T12:00:00Z"),
    _d("b", "2026-07-03T12:00:00Z"),
    _d("c", "2026-07-05T12:00:00Z"),
]


def _ids(docs):
    return {d.id for d in docs}


def test_range_from_to_inclusive():
    out = _filter_docs(DOCS, date_from=date(2026, 7, 1), date_to=date(2026, 7, 3))
    assert _ids(out) == {"a", "b"}


def test_single_day():
    out = _filter_docs(DOCS, date_from=date(2026, 7, 3), date_to=date(2026, 7, 3))
    assert _ids(out) == {"b"}


def test_from_only_onward():
    out = _filter_docs(DOCS, date_from=date(2026, 7, 3))
    assert _ids(out) == {"b", "c"}


def test_to_only():
    out = _filter_docs(DOCS, date_to=date(2026, 7, 3))
    assert _ids(out) == {"a", "b"}


def test_days_back_ignored_when_range_given():
    # days_back would exclude these old docs, but the explicit range wins.
    out = _filter_docs(DOCS, days_back=1, date_from=date(2026, 7, 1), date_to=date(2026, 7, 5))
    assert _ids(out) == {"a", "b", "c"}
