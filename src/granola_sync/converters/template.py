"""Obsidian meeting note template renderer with YAML frontmatter."""

from __future__ import annotations

import yaml
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..api.models import GranolaDocument


def render_meeting_note(
    doc: GranolaDocument,
    markdown_content: str,
    enrichment: dict | None = None,
    transcript_filename: str | None = None,
) -> str:
    """Render a complete Obsidian meeting note with frontmatter.

    Args:
        doc: The Granola document.
        markdown_content: ProseMirror content already converted to Markdown.
        enrichment: Optional Claude AI enrichment data.
        transcript_filename: Optional filename of the transcript note.

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
    action_items = enrichment.get("action_items", []) if enrichment else []
    meeting_type = enrichment.get("meeting_type", "") if enrichment else ""
    follow_ups = enrichment.get("follow_ups", []) if enrichment else []

    # Build frontmatter
    frontmatter: dict = {
        "type": "meeting",
        "date": date_str,
        "time": time_str,
        "source": "granola",
        "granola_id": doc.id,
        "duration": f"{duration}min" if duration else "",
        "participants": participants,
        "projects": projects,
        "status": "processed",
    }
    if tags:
        frontmatter["tags"] = tags
    if meeting_type:
        frontmatter["meeting_type"] = meeting_type

    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Build body
    parts: list[str] = []

    # Title
    parts.append(f"# {doc.title}")
    parts.append("")

    # Context callout
    parts.append("> [!info] Context")
    parts.append(f"> **Date**: {date_str} {time_str}")
    if duration:
        parts.append(f"> **Duration**: {duration} minutes")
    parts.append("> **Source**: Granola")
    parts.append("")

    # Summary (from Granola's AI summary)
    if doc.summary:
        parts.append("## Summary")
        parts.append("")
        parts.append(doc.summary)
        parts.append("")

    # Notes (converted ProseMirror content)
    if markdown_content.strip():
        parts.append("## Notes")
        parts.append("")
        parts.append(markdown_content)
        parts.append("")

    # Action items (from AI enrichment)
    if action_items:
        parts.append("## Action Items")
        parts.append("")
        for item in action_items:
            parts.append(f"- [ ] {item} #todo")
        parts.append("")

    # Follow-ups (from AI enrichment)
    if follow_ups:
        parts.append("## Follow-ups")
        parts.append("")
        for fu in follow_ups:
            parts.append(f"- {fu}")
        parts.append("")

    # References
    if transcript_filename:
        parts.append("## References")
        parts.append("")
        link_name = transcript_filename.replace(".md", "")
        parts.append(f"- [[{link_name}|Full transcript]]")
        parts.append("")

    body = "\n".join(parts)
    return f"---\n{fm_str}---\n\n{body}"
