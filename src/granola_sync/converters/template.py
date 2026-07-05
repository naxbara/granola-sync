"""Obsidian meeting note template renderer with YAML frontmatter."""

from __future__ import annotations

from datetime import timezone
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from ..api.models import GranolaDocument, TranscriptUtterance


def render_meeting_note(
    doc: GranolaDocument,
    markdown_content: str,
    enrichment: dict | None = None,
    utterances: list[TranscriptUtterance] | None = None,
) -> str:
    """Render a complete Obsidian meeting note with frontmatter.

    Args:
        doc: The Granola document.
        markdown_content: ProseMirror content already converted to Markdown.
        enrichment: Optional Claude AI enrichment data.
        utterances: Optional transcript utterances to embed.

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
        updated = updated.replace(tzinfo=timezone.utc)

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

    # Separator + meeting metadata + transcript
    if utterances or participants:
        parts.append("---")
        parts.append("")

        parts.append(
            f"Chat with meeting transcript: "
            f"[https://notes.granola.ai/t/{doc.id}]"
            f"(https://notes.granola.ai/t/{doc.id})"
        )
        parts.append("")

        parts.append(f"Meeting Title: {doc.title}")
        parts.append(f"Date: {date_str}")
        if participants:
            parts.append(f"Meeting participants: {', '.join(participants)}")
        parts.append("")

    # Transcript (embedded in same file), ordered chronologically.
    if utterances:
        parts.append("Transcript:")
        parts.append("")
        for u in sorted(utterances, key=lambda x: x.start_timestamp):
            timestamp = u.start_timestamp.strftime("%H:%M:%S")
            source_label = "You" if u.source == "microphone" else "Speaker"
            parts.append(f"**[{timestamp}]** _{source_label}_: {u.text}")
            parts.append("")

    body = "\n".join(parts)
    return f"---\n{fm_str}---\n\n{body}"
