"""Drive the export: fetch documents, write one .txt per meeting.

Decoupled from the GUI through a progress callback. The runner reports
ExportProgress events so callers (CLI/Tk) can show a progress bar.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ..api.client import GranolaAPIClient
from ..api.models import GranolaDocument
from ..auth.credentials import load_credentials
from ..auth.token_manager import TokenManager
from ..constants import WORKOS_CLIENT_ID
from .txt_formatter import write_document

logger = logging.getLogger(__name__)


@dataclass
class ExportProgress:
    """Progress tick emitted while exporting."""

    current: int
    total: int
    title: str


@dataclass
class ExportResult:
    """Final stats returned to the caller."""

    output_dir: Path
    written_files: list[Path] = field(default_factory=list)
    skipped: int = 0
    errors: int = 0

    @property
    def written(self) -> int:
        return len(self.written_files)


def _filter_docs(
    docs: list[GranolaDocument],
    days_back: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[GranolaDocument]:
    """Filter meetings by an explicit date range or a rolling day window.

    An explicit ``date_from``/``date_to`` (inclusive, compared against the
    meeting's local calendar date) takes precedence. Otherwise ``days_back``
    keeps the last N days (None = all history).
    """
    live = [d for d in docs if not d.deleted_at]

    if date_from is not None or date_to is not None:
        out: list[GranolaDocument] = []
        for d in live:
            md = _as_utc(d.meeting_date).astimezone().date()
            if date_from is not None and md < date_from:
                continue
            if date_to is not None and md > date_to:
                continue
            out.append(d)
        return out

    if days_back is None:
        return live
    cutoff = datetime.now(UTC) - timedelta(days=days_back)
    return [d for d in live if _as_utc(d.meeting_date) >= cutoff]


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def export_documents(
    output_dir: Path,
    credentials_path: Path,
    days_back: int | None = 30,
    include_transcripts: bool = True,
    on_progress: Callable[[ExportProgress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> ExportResult:
    """Fetch Granola meetings and write one .txt per meeting.

    Args:
        output_dir: Where to write the .txt files.
        credentials_path: Path to Granola's supabase.json (the .enc twin will
            be auto-detected and decrypted when newer).
        days_back: How many days back to include. None = all history.
        include_transcripts: Whether to fetch and embed transcripts.
        on_progress: Optional callback for each document processed.
        should_cancel: Optional poll function; if it returns True, stop early.
        date_from: Optional inclusive start date. Takes precedence over days_back.
        date_to: Optional inclusive end date. Takes precedence over days_back.
    """
    tm = TokenManager(credentials_path, WORKOS_CLIENT_ID)
    api = GranolaAPIClient(tm)
    result = ExportResult(output_dir=output_dir)

    try:
        # Touch the token before listing — surfaces auth errors to the GUI early.
        _ = load_credentials(credentials_path)

        all_docs = api.get_documents()
        docs = _filter_docs(all_docs, days_back, date_from, date_to)
        total = len(docs)
        logger.info("Exporting %d/%d documents", total, len(all_docs))

        for i, doc in enumerate(docs, start=1):
            if should_cancel and should_cancel():
                logger.info("Export cancelled by user at %d/%d", i, total)
                break
            if on_progress:
                on_progress(ExportProgress(current=i, total=total, title=doc.title))

            try:
                full = api.get_documents_batch([doc.id])
                full_doc = full[0] if full else doc

                transcript = None
                if include_transcripts:
                    try:
                        transcript = api.get_transcript(doc.id)
                    except Exception as e:
                        logger.warning("Transcript failed for '%s': %s", doc.title, e)
                        transcript = []

                path = write_document(output_dir, full_doc, transcript)
                result.written_files.append(path)
            except Exception as e:
                result.errors += 1
                logger.error("Failed to export '%s' (%s): %s", doc.title, doc.id, e)
    finally:
        api.close()

    return result
