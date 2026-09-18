"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _pin_local_timezone(monkeypatch):
    """Render in UTC by default so results don't depend on the machine's zone.

    Tests that exercise the conversion re-pin it to a real offset.
    """
    from datetime import UTC

    from granola_sync import utils

    monkeypatch.setattr(utils, "LOCAL_TZ", UTC)


@pytest.fixture
def sample_prosemirror() -> dict:
    """Load sample ProseMirror document."""
    return json.loads((FIXTURES_DIR / "sample_prosemirror.json").read_text())


@pytest.fixture
def sample_document_raw() -> dict:
    """Load sample raw document JSON."""
    return json.loads((FIXTURES_DIR / "sample_document.json").read_text())


@pytest.fixture
def sample_transcript_raw() -> list[dict]:
    """Load sample transcript utterances."""
    return json.loads((FIXTURES_DIR / "sample_transcript.json").read_text())


@pytest.fixture
def vault_dir(tmp_path: Path) -> Path:
    """Create a temporary vault directory."""
    return tmp_path
