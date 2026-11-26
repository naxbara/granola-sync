"""Utility functions: slugify, date helpers, platform detection."""

from __future__ import annotations

import platform
from datetime import UTC, datetime, tzinfo
from pathlib import Path

from slugify import slugify as _slugify


def slugify_title(title: str, max_length: int = 80) -> str:
    """Convert a meeting title to a URL/filename-safe slug."""
    return _slugify(title, max_length=max_length, word_boundary=True)


# None = the machine's timezone. Tests pin it so they don't depend on where they run.
LOCAL_TZ: tzinfo | None = None


def to_local(dt: datetime) -> datetime:
    """Convert a datetime to the machine's local timezone.

    Granola returns every timestamp in UTC (``...Z``), calendar starts
    included, so formatting them as-is shifts every note by the UTC offset
    and pushes evening meetings to the next day. Naive values are taken as UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(LOCAL_TZ)


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
    """True when any Granola credentials file (plaintext or encrypted) exists.

    Recent Granola builds ship only encrypted files, and Granola 7.8+ keeps the
    session in stored-accounts.json next to supabase.json, so either may be the
    one present.
    """
    accounts = path.with_name("stored-accounts.json")
    candidates = (path, accounts)
    return any(p.exists() or encrypted_credentials_path(p).exists() for p in candidates)


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
