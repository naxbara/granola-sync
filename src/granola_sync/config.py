"""YAML configuration loader with cross-platform defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .utils import default_credentials_path


@dataclass
class SyncConfig:
    include_transcripts: bool = True
    fuzzy_threshold: int = 85


@dataclass
class EnrichmentConfig:
    enabled: bool = False
    api_key: str = ""
    model: str = "claude-opus-4-8"


@dataclass
class LoggingConfig:
    dir: str = "logs"
    verbose: bool = False


@dataclass
class AppConfig:
    """Top-level application configuration."""

    vault_path: Path = field(default_factory=lambda: Path.cwd())
    credentials_path: Path = field(default_factory=default_credentials_path)
    workos_client_id: str = "client_01JZJ0XBDAT8PHJWQY09Y0VD61"
    sync: SyncConfig = field(default_factory=SyncConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # CLI overrides (not in YAML)
    mode: str = "daily"
    from_date: str | None = None
    dry_run: bool = False
    no_enrich: bool = False

    @classmethod
    def from_yaml(cls, path: Path) -> AppConfig:
        """Load config from a YAML file, merging with defaults."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        config = cls()

        if "vault_path" in data:
            config.vault_path = Path(data["vault_path"]).expanduser()

        if "credentials_path" in data:
            config.credentials_path = Path(data["credentials_path"]).expanduser()

        if "workos_client_id" in data:
            config.workos_client_id = data["workos_client_id"]

        sync_data = data.get("sync", {})
        config.sync = SyncConfig(
            include_transcripts=sync_data.get("include_transcripts", True),
            fuzzy_threshold=sync_data.get("fuzzy_threshold", 85),
        )

        enrich_data = data.get("enrichment", {})
        config.enrichment = EnrichmentConfig(
            enabled=enrich_data.get("enabled", False),
            api_key=enrich_data.get("api_key", ""),
            model=enrich_data.get("model", "claude-sonnet-4-20250514"),
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
        if not self.credentials_path.exists():
            errors.append(f"Credentials file not found: {self.credentials_path}")
        if self.enrichment.enabled and not self.enrichment.api_key:
            errors.append("Enrichment enabled but no api_key provided")
        if self.mode == "historical" and not self.from_date:
            errors.append("Historical mode requires --from date")
        return errors
