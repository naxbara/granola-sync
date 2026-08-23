"""Render the literal transcript as its own vault note.

Since 2026-08-23 the transcript no longer lives inside the meeting note
(Fase 1 of the Segundo Cerebro plan): the note keeps a folded callout that
links to ``Transcripciones/<stem>-transcript.md``.

The format below mirrors what ``extraer-transcripciones.py`` produced for the
482 notes already in the vault — a freshly synced note must be
indistinguishable from a migrated one, so the wording is copied verbatim
(including "Transcripcion" without its accent, which is what the vault has).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..constants import TRANSCRIPT_SUFFIX

if TYPE_CHECKING:
    from ..api.models import GranolaDocument, TranscriptUtterance


def granola_url(doc_id: str) -> str:
    """Public Granola link for a document."""
    return f"https://notes.granola.ai/t/{doc_id}"


def render_meeting_header(
    doc: GranolaDocument, date_str: str, participants: list[str]
) -> list[str]:
    """The Granola preamble (link, title, date, participants) as lines."""
    url = granola_url(doc.id)
    parts = [
        f"Chat with meeting transcript: [{url}]({url})",
        "",
        f"Meeting Title: {doc.title}",
        f"Date: {date_str}",
    ]
    if participants:
        parts.append(f"Meeting participants: {', '.join(participants)}")
    parts.append("")
    return parts


def render_utterances(utterances: list[TranscriptUtterance]) -> list[str]:
    """Transcript lines in chronological order, blank-separated.

    The speaker label is binary because that is all Granola gives us:
    ``source == "microphone"`` is the mic owner, everything else collapses
    into a single "Speaker".
    """
    lines: list[str] = ["Transcript:", ""]
    for u in sorted(utterances, key=lambda x: x.start_timestamp):
        timestamp = u.start_timestamp.strftime("%H:%M:%S")
        source_label = "You" if u.source == "microphone" else "Speaker"
        lines.append(f"**[{timestamp}]** _{source_label}_: {u.text}")
        lines.append("")
    return lines


def render_transcript_note(
    doc: GranolaDocument,
    date_str: str,
    participants: list[str],
    utterances: list[TranscriptUtterance],
    note_stem: str,
) -> str:
    """Render the standalone transcript note for ``Transcripciones/``.

    Args:
        doc: The Granola document.
        date_str: Meeting date as YYYY-MM-DD.
        participants: Participant emails, already resolved.
        utterances: Transcript utterances to render.
        note_stem: Filename stem of the meeting note (no extension), used for
            the backlink so both files stay paired.
    """
    header = [
        "---",
        "type: transcripcion",
        f"date: '{date_str}'",
        "source: granola",
        f"granola_id: {doc.id}",
        f'reunion: "[[{note_stem}]]"',
        "---",
        "",
        f"> Transcripcion literal de [[{note_stem}]]. "
        "Fuera del camino de lectura por defecto.",
        "",
    ]
    body = render_meeting_header(doc, date_str, participants) + render_utterances(utterances)
    content = "\n".join(header + body)
    if not content.endswith("\n"):
        content += "\n"
    return content


def render_callout(doc: GranolaDocument, participants: list[str], note_stem: str) -> str:
    """Render the folded callout that replaces the transcript in the note.

    Field order is fixed (Ver -> Granola -> Meeting participants) to match the
    migrated notes.
    """
    lines = [
        "> [!quote]- Transcripcion completa",
        "> La transcripcion literal de esta reunion vive fuera del camino de lectura",
        "> por defecto para no pesar en las consultas al vault.",
        f"> Ver: [[{transcript_stem(note_stem)}]]",
        f"> Granola: {granola_url(doc.id)}",
    ]
    if participants:
        lines.append(f"> Meeting participants: {', '.join(participants)}")
    return "\n".join(lines) + "\n"


def transcript_stem(note_stem: str) -> str:
    """Filename stem of the transcript paired with a meeting note."""
    return f"{note_stem}{TRANSCRIPT_SUFFIX}"


def transcript_filename(note_stem: str) -> str:
    """Filename of the transcript paired with a meeting note."""
    return f"{transcript_stem(note_stem)}.md"
