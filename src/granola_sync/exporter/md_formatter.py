"""Render a Granola document as an Obsidian-ready Markdown (.md) file.

Reuses the same note renderer as the CLI sync (converters.template) so a file
exported from the GUI is identical to what `granola-sync` writes into a vault —
YAML frontmatter + summary + embedded transcript. Unlike the CLI, this is a
standalone one-shot export: no vault, no dedup, no update tracking.
"""

from __future__ import annotations

from pathlib import Path

from ..api.models import GranolaDocument, TranscriptUtterance
from ..converters.html import html_to_markdown
from ..converters.prosemirror import ProseMirrorToMarkdown
from ..converters.template import render_meeting_note
from ..utils import generate_filename

_converter = ProseMirrorToMarkdown()


def _summary_markdown(doc: GranolaDocument) -> str:
    """Best Markdown summary for the note, in the same priority as the sync."""
    panel = doc.last_viewed_panel
    if panel and panel.content:
        content = panel.content
        if isinstance(content, dict):
            md = _converter.convert(content)
            if md.strip():
                return md
        elif isinstance(content, str):
            md = html_to_markdown(content)
            if md.strip():
                return md

    if doc.notes and isinstance(doc.notes, dict):
        md = _converter.convert(doc.notes)
        if md.strip():
            return md
    if doc.notes_markdown:
        return doc.notes_markdown
    if doc.notes_plain:
        return doc.notes_plain
    if doc.overview:
        return doc.overview
    if doc.summary:
        return doc.summary
    return ""


def write_markdown_document(
    out_dir: Path,
    doc: GranolaDocument,
    transcript: list[TranscriptUtterance] | None,
) -> Path:
    """Write an Obsidian-style `.md` note to out_dir and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md_content = _summary_markdown(doc)
    note = render_meeting_note(doc, md_content, None, transcript)
    date_str = doc.meeting_date.strftime("%Y-%m-%d")
    filename = generate_filename(doc.title, date_str)  # YYYY-MM-DD-slug.md
    path = out_dir / filename
    path.write_text(note, encoding="utf-8")
    return path
