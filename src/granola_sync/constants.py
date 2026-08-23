"""Shared constants used across the CLI and GUI pipelines."""

from __future__ import annotations

# WorkOS OAuth client id for Granola's desktop auth (single source of truth).
WORKOS_CLIENT_ID = "client_01JZJ0XBDAT8PHJWQY09Y0VD61"

# Default Obsidian subfolder the CLI writes meeting notes into.
DEFAULT_NOTES_FOLDER = "Reuniones"

# Default subfolder for the literal transcripts, kept out of the reading path.
DEFAULT_TRANSCRIPTS_FOLDER = "Transcripciones"

# Suffix appended to a note's stem to name its transcript file.
TRANSCRIPT_SUFFIX = "-transcript"
