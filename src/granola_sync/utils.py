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


def encrypted_credentials_path(path: Path) -> Path:
    """Return the encrypted twin (supabase.json.enc) of a credentials path."""
    return path.with_name(path.name + ".enc")


def credentials_exist(path: Path) -> bool:
    """True when the plaintext credentials file or its encrypted twin exists.

    Recent Granola builds ship only the encrypted file, so the plaintext one
    may legitimately be missing.
    """
    return path.exists() or encrypted_credentials_path(path).exists()


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
