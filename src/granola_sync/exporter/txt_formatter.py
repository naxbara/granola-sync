"""Render a Granola document + transcript as a plain-text file.

The format targets non-technical users opening the .txt in Notepad/TextEdit/Word:
  - Title banner with `=` underline
  - Metadata block (date, duration, participants)
  - SUMMARY section with the AI-generated summary
  - TRANSCRIPCION section (optional) with [HH:MM:SS] Speaker: text lines
"""

from __future__ import annotations

import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..api.models import GranolaDocument, TranscriptUtterance
from ..converters.prosemirror import to_plain_text
from ..utils import slugify_title

# Older Granola transcripts embed a "Speaker A: " / "Speaker B: " prefix in the
# text itself. Detect that so we don't double-prefix with our own label.
_EMBEDDED_SPEAKER_RE = re.compile(r"^(Speaker [A-Z]):\s*(.*)", re.DOTALL)


def _html_to_plain_text(content: str) -> str:
    """Best-effort HTML → plain text for legacy Granola panel content.

    Converts <li> to "- ", <h*> to a blank-line-padded line, drops other tags,
    and unescapes HTML entities. Not a real HTML parser — Granola panel HTML
    is consistently shallow (h3/ul/li/p/br/strong/em).
    """
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[ou]l[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<h[1-6][^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h[1-6]>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

_SPANISH_MONTHS = [
    "",
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _format_date_es(dt: datetime) -> str:
    """Format a datetime as '8 de mayo de 2026, 14:30' (local timezone)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    month = _SPANISH_MONTHS[local.month]
    return f"{local.day} de {month} de {local.year}, {local.hour:02d}:{local.minute:02d}"


def _participant_names(doc: GranolaDocument) -> list[str]:
    """Return readable participant names — display name when present, else email."""
    names: list[str] = []
    seen: set[str] = set()

    def _add(entry: dict) -> None:
        name = (entry.get("name") or "").strip()
        email = (entry.get("email") or "").strip()
        label = name or email
        if label and label not in seen:
            seen.add(label)
            names.append(label)

    if doc.people and isinstance(doc.people, dict):
        for att in doc.people.get("attendees", []):
            if isinstance(att, dict):
                _add(att)
    if not names and doc.google_calendar_event:
        cal = doc.google_calendar_event
        if isinstance(cal, dict):
            for att in cal.get("attendees", []):
                if isinstance(att, dict):
                    _add(att)
    return names


def _extract_summary_text(doc: GranolaDocument) -> str:
    """Pick the best human-readable summary content, in priority order.

    Priority: last_viewed_panel (AI summary) > notes (user content) > overview > summary.
    Returns plain text (no markdown markers).
    """
    if doc.last_viewed_panel and doc.last_viewed_panel.content:
        content = doc.last_viewed_panel.content
        if isinstance(content, dict):
            text = to_plain_text(content)
            if text.strip():
                return text
        elif isinstance(content, str):
            text = _html_to_plain_text(content)
            if text.strip():
                return text

    if doc.notes and isinstance(doc.notes, dict):
        text = to_plain_text(doc.notes)
        if text.strip():
            return text

    if doc.notes_plain:
        return doc.notes_plain
    if doc.notes_markdown:
        return doc.notes_markdown
    if doc.overview:
        return doc.overview
    if doc.summary:
        return doc.summary
    return "(Sin resumen disponible)"


def _format_transcript(utterances: list[TranscriptUtterance]) -> str:
    """Render utterances as `[HH:MM:SS] Speaker: text` lines."""
    if not utterances:
        return "(Sin transcripción disponible)"

    lines: list[str] = []
    sorted_uts = sorted(utterances, key=lambda u: u.start_timestamp)
    base = sorted_uts[0].start_timestamp
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)

    for u in sorted_uts:
        ts = u.start_timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        elapsed = int((ts - base).total_seconds())
        h, rem = divmod(max(elapsed, 0), 3600)
        m, s = divmod(rem, 60)

        text = u.text.strip()
        embedded = _EMBEDDED_SPEAKER_RE.match(text)
        if embedded:
            speaker, body = embedded.group(1), embedded.group(2).strip()
        else:
            speaker = "Tú" if u.source == "microphone" else "Otro"
            body = text
        lines.append(f"[{h:02d}:{m:02d}:{s:02d}] {speaker}: {body}")
    return "\n".join(lines)


def format_document(
    doc: GranolaDocument,
    transcript: list[TranscriptUtterance] | None = None,
) -> str:
    """Render a Granola document as the .txt body string."""
    title = doc.title.strip() or "Reunión sin título"
    bar = "=" * 80
    sep = "-" * 80

    metadata_lines = [f"Fecha: {_format_date_es(doc.meeting_date)}"]
    if doc.duration_minutes is not None:
        metadata_lines.append(f"Duración: {doc.duration_minutes} minutos")
    participants = _participant_names(doc)
    if participants:
        metadata_lines.append(f"Participantes: {', '.join(participants)}")

    parts = [
        bar,
        title,
        bar,
        "",
        "\n".join(metadata_lines),
        "",
        sep,
        "RESUMEN",
        sep,
        "",
        _extract_summary_text(doc).strip(),
    ]

    if transcript is not None:
        parts.extend([
            "",
            sep,
            "TRANSCRIPCIÓN",
            sep,
            "",
            _format_transcript(transcript),
        ])

    parts.append("")
    return "\n".join(parts)


def generate_txt_filename(title: str, date_str: str) -> str:
    """`YYYY-MM-DD - slugified-title.txt`."""
    slug = slugify_title(title) or "reunion"
    return f"{date_str} - {slug}.txt"


def write_document(
    out_dir: Path,
    doc: GranolaDocument,
    transcript: list[TranscriptUtterance] | None,
) -> Path:
    """Write the rendered .txt to out_dir and return the file path.

    Windows uses UTF-8-with-BOM so Notepad and Word render accents correctly.
    macOS and Linux use plain UTF-8 (no BOM needed).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = doc.meeting_date.strftime("%Y-%m-%d")
    filename = generate_txt_filename(doc.title, date_str)
    path = out_dir / filename
    encoding = "utf-8-sig" if sys.platform == "win32" else "utf-8"
    path.write_text(format_document(doc, transcript), encoding=encoding)
    return path
