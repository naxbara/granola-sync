"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
