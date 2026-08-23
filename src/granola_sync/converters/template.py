"""Obsidian meeting note template renderer with YAML frontmatter."""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

import yaml

from .transcript import render_callout, render_meeting_header, render_utterances

if TYPE_CHECKING:
    from ..api.models import GranolaDocument, TranscriptUtterance


def render_meeting_note(
    doc: GranolaDocument,
    markdown_content: str,
    enrichment: dict | None = None,
    utterances: list[TranscriptUtterance] | None = None,
    transcript_mode: str = "inline",
    note_stem: str | None = None,
) -> str:
    """Render a complete Obsidian meeting note with frontmatter.

    Args:
        doc: The Granola document.
        markdown_content: ProseMirror content already converted to Markdown.
        enrichment: Optional Claude AI enrichment data.
        utterances: Optional transcript utterances.
        transcript_mode: "inline" embeds the transcript in the note (legacy,
            still used by the GUI exporter), "separate" replaces it with a
            folded callout linking to the standalone transcript note, "none"
            drops it entirely.
        note_stem: Filename stem of this note, required by "separate" mode to
            build the link to its transcript.

    Returns:
        Complete Markdown string ready to write to .md file.
    """
    meeting_date = doc.meeting_date
    date_str = meeting_date.strftime("%Y-%m-%d")
    time_str = meeting_date.strftime("%H:%M")
    duration = doc.duration_minutes
    participants = doc.participant_emails

    # Enrichment data
    projects = enrichment.get("projects", []) if enrichment else []
    tags = enrichment.get("tags", []) if enrichment else []
    meeting_type = enrichment.get("meeting_type", "") if enrichment else ""

    # granola_updated tracks the source doc's updated_at so future syncs can
    # detect content changes and regenerate the note.
    updated = doc.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)

    # Build frontmatter — omit empty optional fields to keep YAML clean.
    frontmatter: dict = {
        "type": "meeting",
        "date": date_str,
        "time": time_str,
        "source": "granola",
        "granola_id": doc.id,
        "granola_updated": updated.isoformat(),
    }
    if duration:
        frontmatter["duration"] = f"{duration}min"
    if participants:
        frontmatter["participants"] = participants
    if projects:
        frontmatter["projects"] = projects
    frontmatter["status"] = "processed"
    if tags:
        frontmatter["tags"] = tags
    if meeting_type:
        frontmatter["meeting_type"] = meeting_type

    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Build body
    parts: list[str] = []

    # Notes content (AI summary from last_viewed_panel, or user notes, or summary text)
    if markdown_content.strip():
        parts.append(markdown_content)
        parts.append("")

    # The transcript either stays here (inline) or moves to its own note and
    # leaves a callout behind (separate). Without utterances there is no
    # transcript note to link to, so the meeting metadata stays in the note.
    separate = transcript_mode == "separate" and utterances and note_stem
    if separate:
        parts.append(render_callout(doc, participants, note_stem))
    elif transcript_mode != "none" and (utterances or participants):
        parts.append("---")
        parts.append("")
        parts.extend(render_meeting_header(doc, date_str, participants))
        if utterances:
            parts.extend(render_utterances(utterances))

    body = "\n".join(parts)
    return f"---\n{fm_str}---\n\n{body}"
