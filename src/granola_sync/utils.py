"""Utility functions: slugify, date helpers, platform detection."""

from __future__ import annotations

import platform
from pathlib import Path

from slugify import slugify as _slugify


def slugify_title(title: str, max_length: int = 80) -> str:
    """Convert a meeting title to a URL/filename-safe slug."""
    return _slugify(title, max_length=max_length, word_boundary=True)


def generate_filename(title: str, date_str: str, suffix: str = "") -> str:
    """Generate YYYY-MM-DD-slugified-title.md filename.

    Args:
        title: Meeting title.
        date_str: Date string in YYYY-MM-DD format.
        suffix: Optional suffix before .md (e.g. "-transcript").
    """
    slug = slugify_title(title)
    return f"{date_str}-{slug}{suffix}.md"


def default_credentials_path() -> Path:
    """Return the default supabase.json path for the current platform."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Granola" / "supabase.json"
    elif system == "Windows":
        import os
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "Granola" / "supabase.json"
        return Path.home() / "AppData" / "Roaming" / "Granola" / "supabase.json"
    else:
        return Path.home() / ".config" / "Granola" / "supabase.json"
