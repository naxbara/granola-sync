"""YAML configuration loader with cross-platform defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .constants import DEFAULT_NOTES_FOLDER, DEFAULT_TRANSCRIPTS_FOLDER, WORKOS_CLIENT_ID
from .utils import credentials_exist, default_credentials_path


@dataclass
class SyncConfig:
    include_transcripts: bool = True
    fuzzy_threshold: int = 85
    notes_folder: str = DEFAULT_NOTES_FOLDER
    transcripts_folder: str = DEFAULT_TRANSCRIPTS_FOLDER
    # separate: transcript lives in its own note, linked from a callout.
    # inline: legacy behaviour, transcript embedded in the meeting note.
    transcript_mode: str = "separate"


@dataclass
class EnrichmentConfig:
    enabled: bool = False
    api_key: str = ""
    model: str = "claude-opus-4-8"


@dataclass
class CalendarConfig:
    """Google Calendar as a participant source.

    Granola only sees the calendars of the account it was signed up with, so
    most meetings arrive with no attendees. Reading Calendar directly recovers
    them. Off by default: it needs an OAuth client to exist first.
    """

    enabled: bool = False
    calendar_id: str = "primary"
    client_secrets_path: str = ""
    token_path: str = "secrets/google_token.json"
    # How far a calendar event's start may sit from the recording's start.
    match_window_minutes: int = 30
    # Minimum fuzzy score between the meeting title and the event summary.
    # 55 comes from measurement, not taste: over a real week the correct but
    # loosely-named match scored 59 ("Geovita presentación" vs "Geovitas y
    # Sebastián Suárez") while the best *wrong* candidate scored 38, so this
    # sits in the gap with room on both sides.
    title_threshold: int = 55


@dataclass
class IndicesConfig:
    """Regenerate the vault's derived indexes after a sync that wrote notes.

    The indexes in the vault's `Indices/` folder (meetings by client, by
    person, timeline, decisions) are built from the frontmatter this sync
    writes, so they go stale the moment a new note lands. Running the
    generator here keeps them fresh without a second scheduled task.

    Deliberately best-effort: a failure here is reported but never fails the
    sync. The notes are the product; the indexes are derived from them and can
    always be rebuilt by hand.
    """

    enabled: bool = False
    # Path to the generator, relative to the vault (or absolute).
    script: str = "Recursos/segundo-cerebro/generar-indices.py"
    timeout_seconds: int = 180


@dataclass
class LoggingConfig:
    dir: str = "logs"
    verbose: bool = False


@dataclass
class AppConfig:
    """Top-level application configuration."""

    vault_path: Path = field(default_factory=lambda: Path.cwd())
    credentials_path: Path = field(default_factory=default_credentials_path)
    workos_client_id: str = WORKOS_CLIENT_ID
    sync: SyncConfig = field(default_factory=SyncConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    indices: IndicesConfig = field(default_factory=IndicesConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # The vault owner's own addresses. Used to tell a one-to-one apart from a
    # group call, which is the only case where the other speaker can be named
    # without guessing.
    owner_emails: list[str] = field(default_factory=list)

    # Directory relative paths resolve against: the config file's own folder,
    # so a scheduled run behaves the same whatever the working directory is.
    base_dir: Path = field(default_factory=lambda: Path.cwd())

    # CLI overrides (not in YAML)
    mode: str = "daily"
    from_date: str | None = None
    to_date: str | None = None
    dry_run: bool = False
    no_enrich: bool = False

    @classmethod
    def from_yaml(cls, path: Path) -> AppConfig:
        """Load config from a YAML file, merging with defaults."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        config = cls()
        config.base_dir = path.resolve().parent

        if "vault_path" in data:
            config.vault_path = Path(data["vault_path"]).expanduser()

        if "credentials_path" in data:
            config.credentials_path = Path(data["credentials_path"]).expanduser()

        if "workos_client_id" in data:
            config.workos_client_id = data["workos_client_id"]

        config.owner_emails = [
            str(email).strip().lower()
            for email in (data.get("owner_emails") or [])
            if str(email).strip()
        ]

        sync_data = data.get("sync", {})
        config.sync = SyncConfig(
            include_transcripts=sync_data.get("include_transcripts", True),
            fuzzy_threshold=sync_data.get("fuzzy_threshold", 85),
            notes_folder=sync_data.get("notes_folder", DEFAULT_NOTES_FOLDER),
            transcripts_folder=sync_data.get(
                "transcripts_folder", DEFAULT_TRANSCRIPTS_FOLDER
            ),
            transcript_mode=sync_data.get("transcript_mode", "separate"),
        )

        enrich_data = data.get("enrichment", {})
        config.enrichment = EnrichmentConfig(
            enabled=enrich_data.get("enabled", False),
            api_key=enrich_data.get("api_key", ""),
            model=enrich_data.get("model", "claude-sonnet-4-20250514"),
        )

        cal_data = data.get("calendar", {})
        config.calendar = CalendarConfig(
            enabled=cal_data.get("enabled", False),
            calendar_id=cal_data.get("calendar_id", "primary"),
            client_secrets_path=cal_data.get("client_secrets_path", ""),
            token_path=cal_data.get("token_path", "secrets/google_token.json"),
            match_window_minutes=cal_data.get("match_window_minutes", 30),
            title_threshold=cal_data.get("title_threshold", 55),
        )

        idx_data = data.get("indices", {})
        config.indices = IndicesConfig(
            enabled=idx_data.get("enabled", False),
            script=idx_data.get(
                "script", "Recursos/segundo-cerebro/generar-indices.py"
            ),
            timeout_seconds=idx_data.get("timeout_seconds", 180),
        )

        log_data = data.get("logging", {})
        config.logging = LoggingConfig(
            dir=log_data.get("dir", "logs"),
            verbose=log_data.get("verbose", False),
        )

        return config

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty = valid)."""
        errors = []
        if not self.vault_path.exists():
            errors.append(f"Vault path does not exist: {self.vault_path}")
        if not credentials_exist(self.credentials_path):
            errors.append(
                f"Credentials file not found: {self.credentials_path} "
                "(nor its .enc twin) — open Granola and sign in at least once"
            )
        if self.sync.transcript_mode not in ("separate", "inline", "none"):
            errors.append(
                f"Unknown sync.transcript_mode: {self.sync.transcript_mode} "
                "(expected separate, inline or none)"
            )
        if self.enrichment.enabled and not self.enrichment.api_key:
            errors.append("Enrichment enabled but no api_key provided")
        if self.calendar.enabled and not self.calendar.client_secrets_path:
            errors.append(
                "Calendar enabled but no calendar.client_secrets_path provided "
                "(path to the Google OAuth client JSON)"
            )
        if self.mode == "historical" and not self.from_date:
            errors.append("Historical mode requires --from date")
        return errors
