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

import logging
from typing import TYPE_CHECKING

from ..constants import TRANSCRIPT_SUFFIX
from .people import Participant, emails, roster
from .speakers import (
    ATTRIBUTION_CONFIRMED,
    ATTRIBUTION_NONE,
    ATTRIBUTION_SUGGESTED,
    GENERIC_LABEL,
    Candidate,
    resolve_speaker,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..api.models import GranolaDocument, TranscriptUtterance


def granola_url(doc_id: str) -> str:
    """Public Granola link for a document."""
    return f"https://notes.granola.ai/t/{doc_id}"


def _yaml_quote(value: str) -> str:
    """Double-quote a scalar so free text cannot break the frontmatter."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _roster_line(participants: list[Participant]) -> str | None:
    """The named roster, or None when we only ever learned addresses.

    Only people we can actually name go here — the bare addresses are already
    on the ``Meeting participants`` line right above, and repeating them adds
    noise without adding a fact. Keeping the line conditional also means a
    meeting with no identified names renders exactly like the notes migrated
    in August, so the vault stays uniform.
    """
    named = [person for person in participants if person.name]
    if not named:
        return None
    # Someone who joined under two addresses is still one person here, even
    # though both addresses stay on the participants list above: that list is
    # the identity key the vault matches on, this line is for a human.
    seen: set[str] = set()
    once = [p for p in named if not (p.name in seen or seen.add(p.name))]
    return f"Asistentes: {roster(once)}"


def render_meeting_header(
    doc: GranolaDocument, date_str: str, participants: list[Participant]
) -> list[str]:
    """The Granola preamble (link, title, date, attendees) as lines."""
    url = granola_url(doc.id)
    parts = [
        f"Chat with meeting transcript: [{url}]({url})",
        "",
        f"Meeting Title: {doc.title}",
        f"Date: {date_str}",
    ]
    if participants:
        parts.append(f"Meeting participants: {', '.join(emails(participants))}")
    named = _roster_line(participants)
    if named:
        # Whoever reads the transcript needs to know who the Speakers are.
        parts.append(named)
    parts.append("")
    return parts



def render_utterances(
    utterances: list[TranscriptUtterance], speaker_label: str = GENERIC_LABEL
) -> list[str]:
    """Transcript lines in chronological order, blank-separated.

    ``source == "microphone"`` is the mic owner and always renders as "You",
    which is what the 482 migrated transcripts use. Everything else takes the
    label resolved for this meeting, or its own name when Granola provides one.
    """
    lines: list[str] = ["Transcript:", ""]
    for u in sorted(utterances, key=lambda x: x.start_timestamp):
        timestamp = u.start_timestamp.strftime("%H:%M:%S")
        if u.source == "microphone":
            source_label = "You"
        else:
            source_label = u.detected_speaker_name or speaker_label
        lines.append(f"**[{timestamp}]** _{source_label}_: {u.text}")
        lines.append("")
    return lines


def render_transcript_note(
    doc: GranolaDocument,
    date_str: str,
    participants: list[Participant],
    utterances: list[TranscriptUtterance],
    note_stem: str,
    owner_emails: set[str] | None = None,
    candidates: list[Candidate] | None = None,
    confirmed_speaker: str | None = None,
) -> str:
    """Render the standalone transcript note for ``Transcripciones/``.

    Args:
        doc: The Granola document.
        date_str: Meeting date as YYYY-MM-DD.
        participants: Attendees, already resolved.
        utterances: Transcript utterances to render.
        note_stem: Filename stem of the meeting note (no extension), used for
            the backlink so both files stay paired.
        owner_emails: The vault owner's own addresses, so a one-to-one can be
            told apart from a group call.
        candidates: Names that might be the other speaker, recorded in the
            frontmatter for the user to confirm. Never applied on their own.
        confirmed_speaker: A name the user already confirmed. Survives a
            resync — regenerating the note must not silently undo the answer.
    """
    if confirmed_speaker:
        speaker_label, attribution = confirmed_speaker, ATTRIBUTION_CONFIRMED
    else:
        speaker_label, attribution = resolve_speaker(participants, utterances, owner_emails)
        if attribution == ATTRIBUTION_NONE and candidates:
            # A suggestion changes the metadata, never the label: the body
            # keeps saying "Speaker" until a human says otherwise.
            attribution = ATTRIBUTION_SUGGESTED

    header = [
        "---",
        "type: transcripcion",
        f"date: '{date_str}'",
        "source: granola",
        f"granola_id: {doc.id}",
        f'reunion: "[[{note_stem}]]"',
    ]
    # Only recorded when it says something. Absent means the generic "Speaker",
    # which is also what the migrated transcripts carry.
    if attribution != ATTRIBUTION_NONE:
        header.append(f"speaker_attribution: {attribution}")
    if attribution == ATTRIBUTION_CONFIRMED:
        header.append(f"speaker_confirmed: {speaker_label}")
    elif attribution == ATTRIBUTION_SUGGESTED and candidates:
        # Both values are quoted: the evidence string starts with a quoted
        # token ("'marshall' en el título…") and would otherwise be read as a
        # malformed YAML scalar, taking the whole frontmatter down with it.
        names = ", ".join(_yaml_quote(c.name) for c in candidates)
        header.append(f"speaker_candidates: [{names}]")
        header.append(f"speaker_evidence: {_yaml_quote(candidates[0].evidence())}")
    header += [
        "---",
        "",
        f"> Transcripcion literal de [[{note_stem}]]. "
        "Fuera del camino de lectura por defecto.",
        "",
    ]
    body = render_meeting_header(doc, date_str, participants) + render_utterances(
        utterances, speaker_label
    )
    content = "\n".join(header + body)
    if not content.endswith("\n"):
        content += "\n"
    return content


def render_callout(
    doc: GranolaDocument, participants: list[Participant], note_stem: str
) -> str:
    """Render the folded callout that replaces the transcript in the note.

    Field order is fixed (Ver -> Granola -> Meeting participants -> Asistentes)
    to match the migrated notes, which end at Meeting participants.
    """
    lines = [
        "> [!quote]- Transcripcion completa",
        "> La transcripcion literal de esta reunion vive fuera del camino de lectura",
        "> por defecto para no pesar en las consultas al vault.",
        f"> Ver: [[{transcript_stem(note_stem)}]]",
        f"> Granola: {granola_url(doc.id)}",
    ]
    if participants:
        lines.append(f"> Meeting participants: {', '.join(emails(participants))}")
    named = _roster_line(participants)
    if named:
        lines.append(f"> {named}")
    return "\n".join(lines) + "\n"


def transcript_stem(note_stem: str) -> str:
    """Filename stem of the transcript paired with a meeting note."""
    return f"{note_stem}{TRANSCRIPT_SUFFIX}"


def transcript_filename(note_stem: str) -> str:
    """Filename of the transcript paired with a meeting note."""
    return f"{transcript_stem(note_stem)}.md"
