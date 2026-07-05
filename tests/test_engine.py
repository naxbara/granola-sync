"""Tests for the sync engine: skip / create / update / dry-run."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from granola_sync.api.models import GranolaDocument
from granola_sync.config import AppConfig
from granola_sync.sync.engine import SyncEngine


class FakeAPI:
    """Records calls and serves canned documents."""

    def __init__(self, docs: list[GranolaDocument]) -> None:
        self.docs = docs
        self.batch_calls: list[list[str]] = []
        self.transcript_calls: list[str] = []

    def get_documents(self) -> list[GranolaDocument]:
        return self.docs

    def get_documents_batch(self, ids: list[str]) -> list[GranolaDocument]:
        self.batch_calls.append(list(ids))
        return [d for d in self.docs if d.id in ids]

    def get_transcript(self, doc_id: str):
        self.transcript_calls.append(doc_id)
        return []


def _doc(doc_id: str, *, created: datetime, updated: datetime, title="Reunión") -> GranolaDocument:
    return GranolaDocument(id=doc_id, title=title, created_at=created, updated_at=updated)


def _config(vault: Path, **overrides) -> AppConfig:
    cfg = AppConfig()
    cfg.vault_path = vault
    cfg.sync.include_transcripts = False  # keep tests focused on create/update
    cfg.mode = "daily"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _write_note(vault: Path, doc_id: str, updated_iso: str, folder="Reuniones") -> Path:
    notes = vault / folder
    notes.mkdir(parents=True, exist_ok=True)
    path = notes / f"{doc_id}.md"
    path.write_text(
        f"---\ntype: meeting\ngranola_id: {doc_id}\n"
        f"granola_updated: {updated_iso}\n---\n\nold body\n",
        encoding="utf-8",
    )
    return path


def test_creates_new_note(tmp_path: Path):
    now = datetime.now(UTC)
    doc = _doc("d1", created=now, updated=now)
    api = FakeAPI([doc])
    engine = SyncEngine(_config(tmp_path), api)

    engine.run()

    assert engine.stats.new == 1
    assert api.batch_calls == [["d1"]]
    assert list((tmp_path / "Reuniones").glob("*.md"))


def test_skips_unchanged_existing(tmp_path: Path):
    now = datetime.now(UTC)
    _write_note(tmp_path, "d1", now.isoformat())
    doc = _doc("d1", created=now, updated=now)  # not newer than stored
    api = FakeAPI([doc])
    engine = SyncEngine(_config(tmp_path), api)

    engine.run()

    assert engine.stats.skipped == 1
    assert engine.stats.updated == 0
    assert api.batch_calls == []  # nothing hydrated


def test_updates_when_source_newer(tmp_path: Path):
    now = datetime.now(UTC)
    _write_note(tmp_path, "d1", (now - timedelta(hours=1)).isoformat())
    doc = _doc("d1", created=now, updated=now)  # newer than stored
    api = FakeAPI([doc])
    engine = SyncEngine(_config(tmp_path), api)

    engine.run()

    assert engine.stats.updated == 1
    assert engine.stats.new == 0
    body = (tmp_path / "Reuniones" / "d1.md").read_text(encoding="utf-8")
    assert "old body" not in body  # regenerated in place


def test_dry_run_makes_no_api_calls_or_writes(tmp_path: Path):
    now = datetime.now(UTC)
    doc = _doc("d1", created=now, updated=now)
    api = FakeAPI([doc])
    engine = SyncEngine(_config(tmp_path, dry_run=True), api)

    engine.run()

    assert engine.stats.new == 1
    assert api.batch_calls == []  # no detail hydration
    assert api.transcript_calls == []  # no transcript
    assert not (tmp_path / "Reuniones").exists()  # nothing written


def test_document_tolerates_null_title():
    now = datetime.now(UTC)
    doc = GranolaDocument(id="d1", title=None, created_at=now, updated_at=now)
    assert doc.title == ""


def test_historical_respects_from_and_to(tmp_path: Path):
    docs = [
        _doc("a", created=datetime(2026, 7, 1, 12, tzinfo=UTC), updated=datetime(2026, 7, 1, 12, tzinfo=UTC), title="Uno"),
        _doc("b", created=datetime(2026, 7, 3, 12, tzinfo=UTC), updated=datetime(2026, 7, 3, 12, tzinfo=UTC), title="Dos"),
        _doc("c", created=datetime(2026, 7, 5, 12, tzinfo=UTC), updated=datetime(2026, 7, 5, 12, tzinfo=UTC), title="Tres"),
    ]
    api = FakeAPI(docs)
    cfg = _config(tmp_path, mode="historical", from_date="2026-07-01", to_date="2026-07-03")
    engine = SyncEngine(cfg, api)

    engine.run()

    # "a" and "b" fall in [07-01, 07-03]; "c" (07-05) is excluded.
    assert engine.stats.new == 2
    hydrated = [doc_id for call in api.batch_calls for doc_id in call]
    assert set(hydrated) == {"a", "b"}


def test_daily_skips_docs_older_than_24h(tmp_path: Path):
    old = datetime(2020, 1, 1, tzinfo=UTC)
    doc = _doc("d1", created=old, updated=old)
    api = FakeAPI([doc])
    engine = SyncEngine(_config(tmp_path), api)

    engine.run()

    assert engine.stats.new == 0
    assert engine.stats.skipped == 1
