"""Obsidian vault file operations."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def write_note_atomic(vault_path: Path, filename: str, content: str) -> Path:
    """Write a note to the vault using atomic write (tmp + replace).

    Args:
        vault_path: Root directory of the Obsidian vault.
        filename: The target filename (e.g. "2026-02-06-meeting-title.md").
        content: The full Markdown content to write.

    Returns:
        The path of the written file.
    """
    target = vault_path / filename
    tmp = target.with_suffix(".tmp")

    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)
        logger.debug("Wrote %s", target)
    except OSError:
        # On some Windows configs, replace() fails if target exists
        # Fall back to direct write
        if tmp.exists():
            tmp.unlink()
        target.write_text(content, encoding="utf-8")
        logger.debug("Wrote %s (direct)", target)

    return target
