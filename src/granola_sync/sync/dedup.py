"""Duplicate detection for Granola documents in the Obsidian vault.

Matching strategy (in priority order):
1. Exact match by granola_id in YAML frontmatter
2. Date prefix + fuzzy title match (>threshold similarity)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from thefuzz import fuzz

logger = logging.getLogger(__name__)


def extract_granola_id(file_path: Path) -> str | None:
    """Extract granola_id from YAML frontmatter of a .md file."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    if not content.startswith("---"):
        return None

    end = content.find("---", 3)
    if end == -1:
        return None

    try:
        data = yaml.safe_load(content[3:end])
        if isinstance(data, dict):
            return data.get("granola_id")
    except yaml.YAMLError:
        pass

    return None


def scan_vault_for_granola_ids(vault_path: Path) -> dict[str, Path]:
    """Scan all .md files in vault root for granola_id frontmatter.

    Only scans the root directory (no subdirectories) per user requirement.

    Returns:
        Dict mapping granola_id → file path.
    """
    id_map: dict[str, Path] = {}
    for md_file in vault_path.glob("*.md"):
        gid = extract_granola_id(md_file)
        if gid:
            id_map[gid] = md_file
    return id_map


def fuzzy_match_title(
    title: str,
    date_str: str,
    existing_files: list[Path],
    threshold: int = 85,
) -> Path | None:
    """Find a file with matching date prefix and similar title.

    Args:
        title: The meeting title to match.
        date_str: Date string (YYYY-MM-DD) to filter by.
        existing_files: List of .md file paths to search.
        threshold: Minimum fuzzy match score (0-100).

    Returns:
        The matching file path, or None if no match.
    """
    best_score = 0
    best_match = None

    for fp in existing_files:
        stem = fp.stem
        # Only consider files starting with the same date
        if not stem.startswith(date_str):
            continue

        # Extract the title part after the date prefix
        match = re.match(r"\d{4}-\d{2}-\d{2}-(.*)", stem)
        if not match:
            continue

        existing_title = match.group(1).replace("-", " ")
        score = fuzz.ratio(title.lower(), existing_title.lower())

        if score > best_score:
            best_score = score
            best_match = fp

    if best_score >= threshold:
        logger.debug(
            "Fuzzy match: '%s' → '%s' (score=%d)",
            title,
            best_match.name if best_match else "None",
            best_score,
        )
        return best_match

    return None
