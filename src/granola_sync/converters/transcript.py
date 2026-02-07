"""Convert transcript utterances to Markdown format."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..api.models import TranscriptUtterance


def format_transcript(utterances: list[TranscriptUtterance], title: str) -> str:
    """Format transcript utterances into a readable Markdown document.

    Args:
        utterances: List of transcript utterances sorted by time.
        title: Meeting title for the document header.

    Returns:
        Markdown string with timestamped utterances.
    """
    lines = [
        "---",
        "type: transcript",
        "source: granola",
        "---",
        "",
        f"# Transcript: {title}",
        "",
    ]

    for u in utterances:
        timestamp = u.start_timestamp.strftime("%H:%M:%S")
        source_label = "You" if u.source == "microphone" else "Speaker"
        lines.append(f"**[{timestamp}]** _{source_label}_: {u.text}")
        lines.append("")

    return "\n".join(lines)
