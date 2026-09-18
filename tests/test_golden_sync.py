"""Golden snapshot of a full sync: the meeting note and its transcript, byte for byte.

Baseline for Phase 1 of Planes/Plan-Producto-Segundo-Cerebro-Sep2026.md: once granola_sync
reads its folders, owner and strings from a vault profile, the default profile must still
produce exactly these files. Regenerate on purpose with UPDATE_GOLDEN=1.
"""

from __future__ import annotations

import json
import os
from datetime import timedelta, timezone
from pathlib import Path

import pytest

from granola_sync import utils
from granola_sync.api.models import GranolaDocument, TranscriptUtterance
from granola_sync.config import AppConfig
from granola_sync.sync.engine import SyncEngine

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden_sync"


class FakeAPI:
    def __init__(self, doc: GranolaDocument, utterances: list[TranscriptUtterance]) -> None:
        self.doc = doc
        self.utterances = utterances

    def get_documents(self):
        return [self.doc]

    def get_documents_batch(self, ids):
        return [self.doc] if self.doc.id in ids else []

    def get_transcript(self, doc_id):
        return self.utterances


@pytest.fixture(autouse=True)
def _santiago(monkeypatch):
    monkeypatch.setattr(utils, "LOCAL_TZ", timezone(timedelta(hours=-3)))


def _run_sync(vault: Path) -> dict[str, str]:
    doc = GranolaDocument(**json.loads((FIXTURES / "sample_document.json").read_text("utf-8")))
    utterances = [
        TranscriptUtterance(**u)
        for u in json.loads((FIXTURES / "sample_transcript.json").read_text("utf-8"))
    ]
    cfg = AppConfig()
    cfg.vault_path = vault
    cfg.mode = "historical"
    cfg.from_date = "2026-02-01"
    cfg.to_date = "2026-02-28"
    cfg.owner_emails = ["sebastian@example.com"]
    SyncEngine(cfg, FakeAPI(doc, utterances)).run()
    return {
        p.relative_to(vault).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(vault.rglob("*.md"))
    }


def test_sync_output_matches_golden(tmp_path: Path):
    written = _run_sync(tmp_path)
    assert written, "the sync wrote nothing"

    if os.environ.get("UPDATE_GOLDEN"):
        for rel, text in written.items():
            target = GOLDEN / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))

    expected = {
        # read_text, not read_bytes: a CRLF checkout (core.autocrlf) must not fail the test
        p.relative_to(GOLDEN).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(GOLDEN.rglob("*.md"))
    }
    assert sorted(written) == sorted(expected)
    for rel, text in written.items():
        assert text == expected[rel], f"{rel} differs from its golden snapshot"
