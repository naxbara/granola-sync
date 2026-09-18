"""from_yaml repeats every default as a literal; these tests keep both copies in step.

Found 2026-09-17: the dataclass said one enrichment model and from_yaml another, retired one.
It went unnoticed only because enrichment is off.
"""

from dataclasses import fields

import pytest

from granola_sync.config import (
    AppConfig,
    CalendarConfig,
    EnrichmentConfig,
    IndicesConfig,
    LoggingConfig,
    SyncConfig,
)

SECTIONS = {
    "sync": SyncConfig,
    "enrichment": EnrichmentConfig,
    "calendar": CalendarConfig,
    "indices": IndicesConfig,
    "logging": LoggingConfig,
}


@pytest.mark.parametrize("empty_section", [False, True], ids=["missing", "empty"])
@pytest.mark.parametrize("name,cls", SECTIONS.items())
def test_yaml_defaults_match_dataclass(tmp_path, name, cls, empty_section):
    path = tmp_path / "config.yaml"
    path.write_text(f"{name}: {{}}\n" if empty_section else "", encoding="utf-8")
    loaded = getattr(AppConfig.from_yaml(path), name)
    for f in fields(cls):
        assert getattr(loaded, f.name) == getattr(cls(), f.name), f"{name}.{f.name}"


def test_yaml_values_override_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("enrichment:\n  model: otro-modelo\n", encoding="utf-8")
    assert AppConfig.from_yaml(path).enrichment.model == "otro-modelo"
