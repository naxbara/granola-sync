"""The sync reads the vault profile (sc_vault) when it is installed, and ignores it otherwise.

Precedence: config.yaml > <vault>/vault.yaml > built-in defaults. Without sc_vault, or with a
profile that does not load, the sync must behave exactly as before the profile existed.
"""

from __future__ import annotations

import builtins
from datetime import UTC, datetime
from pathlib import Path

import pytest

from granola_sync import utils, vocab
from granola_sync.api.models import GranolaDocument, TranscriptUtterance
from granola_sync.config import AppConfig, load_vault_profile
from granola_sync.converters.transcript import render_callout, render_transcript_note
from granola_sync.sync.engine import SyncEngine


def _config_file(tmp_path: Path, body: str = "") -> Path:
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"vault_path: '{vault.as_posix()}'\n{body}", encoding="utf-8")
    return cfg


def _profile(tmp_path: Path, text: str) -> None:
    (tmp_path / "vault").mkdir(exist_ok=True)
    (tmp_path / "vault" / "vault.yaml").write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _restore_vocab():
    yield
    vocab.use("es")


def test_no_profile_keeps_the_built_in_defaults(tmp_path):
    cfg = AppConfig.from_yaml(_config_file(tmp_path))
    assert (cfg.sync.notes_folder, cfg.sync.transcripts_folder, cfg.sync.people_folder) == (
        "Reuniones", "Transcripciones", "Personas")
    assert cfg.language == "es" and cfg.timezone is None and cfg.owner_emails == []


def test_without_sc_vault_the_profile_is_ignored(tmp_path, monkeypatch):
    _profile(tmp_path, "language: en\n")
    real_import = builtins.__import__

    def no_sc_vault(name, *args, **kwargs):
        if name.startswith("sc_vault"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_sc_vault)
    cfg = AppConfig.from_yaml(_config_file(tmp_path))
    assert cfg.language == "es" and cfg.sync.notes_folder == "Reuniones"


def test_broken_profile_falls_back_instead_of_failing(tmp_path):
    pytest.importorskip("sc_vault")
    _profile(tmp_path, "language: klingon\n")
    assert load_vault_profile(tmp_path / "vault") is None
    assert AppConfig.from_yaml(_config_file(tmp_path)).sync.notes_folder == "Reuniones"


def test_profile_fills_what_config_yaml_leaves_out(tmp_path):
    pytest.importorskip("sc_vault")
    _profile(tmp_path, (
        "language: en\ntimezone: America/Santiago\n"
        "owner: {name: Jane, emails: [Jane@Example.com]}\n"
        "folders: {people: Contacts}\n"))
    cfg = AppConfig.from_yaml(_config_file(tmp_path))
    assert cfg.language == "en" and cfg.timezone == "America/Santiago"
    assert cfg.sync.notes_folder == "Meetings"
    assert cfg.sync.transcripts_folder == "Transcripts"
    assert cfg.sync.people_folder == "Contacts"
    assert cfg.owner_emails == ["jane@example.com"]


def test_config_yaml_wins_over_the_profile(tmp_path):
    pytest.importorskip("sc_vault")
    _profile(tmp_path, "language: en\nowner: {emails: [jane@example.com]}\n")
    cfg = AppConfig.from_yaml(_config_file(tmp_path, (
        "owner_emails: [me@example.com]\n"
        "sync:\n  transcripts_folder: Transcripciones\n")))
    assert cfg.sync.transcripts_folder == "Transcripciones"
    assert cfg.sync.notes_folder == "Meetings"
    assert cfg.owner_emails == ["me@example.com"]


def test_engine_applies_language_and_timezone(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "LOCAL_TZ", UTC)
    cfg = AppConfig()
    cfg.vault_path = tmp_path
    cfg.language, cfg.timezone = "en", "America/Santiago"
    SyncEngine(cfg, api=None)
    assert vocab.ACTIVE is vocab.VOCABS["en"]
    assert str(utils.LOCAL_TZ) == "America/Santiago"


def test_engine_leaves_the_machine_zone_alone_without_a_timezone(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "LOCAL_TZ", UTC)
    cfg = AppConfig()
    cfg.vault_path = tmp_path
    SyncEngine(cfg, api=None)
    assert utils.LOCAL_TZ is UTC


def test_english_vault_writes_english_transcript_notes():
    vocab.use("en")
    doc = GranolaDocument(id="d1", title="Kickoff", created_at="2026-03-02T15:00:00Z",
                          updated_at="2026-03-02T16:00:00Z")
    utterances = [TranscriptUtterance(
        id="u1", document_id="d1", start_timestamp=datetime(2026, 3, 2, 15, tzinfo=UTC),
        end_timestamp=datetime(2026, 3, 2, 15, 0, 5, tzinfo=UTC), text="Hi", source="system")]

    note = render_transcript_note(doc, "2026-03-02", [], utterances, "2026-03-02-kickoff")
    assert "type: transcript\n" in note
    assert 'meeting: "[[2026-03-02-kickoff]]"' in note
    assert "> Literal transcript of [[2026-03-02-kickoff]]." in note

    callout = render_callout(doc, [], "2026-03-02-kickoff")
    assert callout.startswith("> [!quote]- Full transcript\n")
    assert "> See: [[2026-03-02-kickoff-transcript]]" in callout
    assert not any(w in note + callout for w in ("Transcripcion", "reunion", "Ver:"))
