"""Tests for regenerating the vault's derived indexes after a sync.

The rule these enforce: the indexes are derived data, so refreshing them may
never break the thing that produces the real data. Every failure mode — script
missing, non-zero exit, timeout, OS error — has to come back as a reported
warning, not an exception that takes the sync down with it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from granola_sync.config import AppConfig, IndicesConfig
from granola_sync.sync.indices import regenerate

SCRIPT_NAME = "generar-indices.py"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    (tmp_path / "Recursos" / "segundo-cerebro").mkdir(parents=True)
    return tmp_path


def _config(vault: Path, **kwargs) -> AppConfig:
    config = AppConfig()
    config.vault_path = vault
    config.indices = IndicesConfig(
        enabled=kwargs.pop("enabled", True),
        engine=kwargs.pop("engine", "script"),
        script=kwargs.pop("script", f"Recursos/segundo-cerebro/{SCRIPT_NAME}"),
        timeout_seconds=kwargs.pop("timeout_seconds", 180),
    )
    config.dry_run = kwargs.pop("dry_run", False)
    return config


def _write_script(vault: Path, body: str, name: str = SCRIPT_NAME) -> Path:
    path = vault / "Recursos" / "segundo-cerebro" / name
    path.write_text(body, encoding="utf-8")
    return path


# --- when it must NOT run ------------------------------------------------


def test_skips_when_disabled(vault: Path):
    _write_script(vault, "raise SystemExit(0)")
    result = regenerate(_config(vault, enabled=False), wrote_notes=True)
    assert not result.ran
    assert not result.failed


def test_skips_on_dry_run(vault: Path):
    """A dry-run promises to write nothing. That includes the indexes."""
    marker = vault / "ran.txt"
    _write_script(vault, f"open(r'{marker}', 'w').close()")
    result = regenerate(_config(vault, dry_run=True), wrote_notes=True)
    assert not result.ran
    assert not marker.exists()


def test_skips_when_nothing_was_written(vault: Path):
    """No new or updated notes means the indexes already match the vault."""
    marker = vault / "ran.txt"
    _write_script(vault, f"open(r'{marker}', 'w').close()")
    result = regenerate(_config(vault), wrote_notes=False)
    assert not result.ran
    assert result.reason == "no notes written"
    assert not marker.exists()


# --- when it runs --------------------------------------------------------


def test_runs_and_reports_success(vault: Path):
    marker = vault / "ran.txt"
    _write_script(vault, f"open(r'{marker}', 'w').close()")
    result = regenerate(_config(vault), wrote_notes=True)
    assert result.ran and result.ok
    assert marker.exists()


def test_passes_vault_and_apply(vault: Path):
    """Without --apply the generator is a dry-run and would write nothing."""
    args_file = vault / "args.txt"
    _write_script(
        vault,
        "import sys\n"
        f"open(r'{args_file}', 'w', encoding='utf-8').write('\\n'.join(sys.argv[1:]))\n",
    )
    regenerate(_config(vault), wrote_notes=True)
    args = args_file.read_text(encoding="utf-8").splitlines()
    assert "--apply" in args
    assert "--vault" in args
    assert str(vault) in args


def test_accepts_absolute_script_path(vault: Path, tmp_path: Path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    script = outside / SCRIPT_NAME
    script.write_text("raise SystemExit(0)", encoding="utf-8")
    result = regenerate(_config(vault, script=str(script)), wrote_notes=True)
    assert result.ran and result.ok


# --- failure modes: reported, never raised -------------------------------


def test_missing_script_is_reported_not_raised(vault: Path):
    result = regenerate(_config(vault, script="nope/missing.py"), wrote_notes=True)
    assert result.failed
    assert "not found" in result.reason


def test_non_zero_exit_is_reported_not_raised(vault: Path):
    _write_script(
        vault,
        "import sys\nsys.stderr.write('boom: bad frontmatter\\n')\nraise SystemExit(2)",
    )
    result = regenerate(_config(vault), wrote_notes=True)
    assert result.failed
    assert "boom: bad frontmatter" in result.reason


def test_timeout_is_reported_not_raised(vault: Path, monkeypatch):
    _write_script(vault, "raise SystemExit(0)")

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="generar-indices.py", timeout=1)

    monkeypatch.setattr(subprocess, "run", _timeout)
    result = regenerate(_config(vault, timeout_seconds=1), wrote_notes=True)
    assert result.failed
    assert "timed out" in result.reason


def test_os_error_is_reported_not_raised(vault: Path, monkeypatch):
    _write_script(vault, "raise SystemExit(0)")

    def _boom(*args, **kwargs):
        raise OSError("no interpreter")

    monkeypatch.setattr(subprocess, "run", _boom)
    result = regenerate(_config(vault), wrote_notes=True)
    assert result.failed
    assert "no interpreter" in result.reason


def test_uses_the_running_interpreter(vault: Path):
    """A venv sync must not shell out to some other Python on PATH."""
    out = vault / "which.txt"
    _write_script(
        vault,
        f"import sys\nopen(r'{out}', 'w', encoding='utf-8').write(sys.executable)\n",
    )
    regenerate(_config(vault), wrote_notes=True)
    assert out.read_text(encoding="utf-8") == sys.executable


# --- a failed attempt is retried ------------------------------------------


def test_failure_leaves_a_marker(vault: Path):
    pending = vault / "logs" / "indices_pending"
    _write_script(vault, "raise SystemExit(2)")
    result = regenerate(_config(vault), wrote_notes=True, pending=pending)
    assert result.failed
    assert pending.exists()


def test_marker_retries_without_new_notes(vault: Path):
    """2026-10-30: one failure, then two days with no notes and no retry."""
    pending = vault / "indices_pending"
    pending.write_text("index generator failed: earlier\n", encoding="utf-8")
    marker = vault / "ran.txt"
    _write_script(vault, f"open(r'{marker}', 'w').close()")
    result = regenerate(_config(vault), wrote_notes=False, pending=pending)
    assert result.ran and result.ok
    assert marker.exists()
    assert not pending.exists()


def test_marker_stays_while_it_keeps_failing(vault: Path):
    pending = vault / "indices_pending"
    pending.write_text("index generator failed: earlier\n", encoding="utf-8")
    _write_script(vault, "import sys\nsys.stderr.write('still broken\\n')\nraise SystemExit(2)")
    result = regenerate(_config(vault), wrote_notes=False, pending=pending)
    assert result.failed
    assert "still broken" in pending.read_text(encoding="utf-8")


def test_no_marker_no_retry(vault: Path):
    marker = vault / "ran.txt"
    _write_script(vault, f"open(r'{marker}', 'w').close()")
    result = regenerate(_config(vault), wrote_notes=False, pending=vault / "indices_pending")
    assert not result.ran
    assert not marker.exists()


def test_dry_run_does_not_retry(vault: Path):
    pending = vault / "indices_pending"
    pending.write_text("x\n", encoding="utf-8")
    result = regenerate(_config(vault, dry_run=True), wrote_notes=False, pending=pending)
    assert not result.ran
    assert pending.exists()


def test_stderr_on_success_comes_back_as_warnings(vault: Path):
    """sc_vault skips a note it cannot open and says so on stderr, exit 0."""
    _write_script(
        vault, "import sys\nsys.stderr.write('sc_vault: skipped unreadable note X.md\\n')\n"
    )
    result = regenerate(_config(vault), wrote_notes=True)
    assert result.ok
    assert result.warnings == ["sc_vault: skipped unreadable note X.md"]


# --- engine: script | sc_vault | auto -------------------------------------


def _capture_cmd(monkeypatch) -> list:
    seen: list = []

    def _run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", _run)
    return seen


def test_engine_sc_vault_runs_the_module(vault: Path, monkeypatch):
    monkeypatch.setattr("granola_sync.sync.indices._sc_vault_installed", lambda: True)
    seen = _capture_cmd(monkeypatch)
    result = regenerate(_config(vault, engine="sc_vault"), wrote_notes=True)
    assert result.ok
    assert seen == [[sys.executable, "-m", "sc_vault", "indices", "--vault", str(vault), "--apply"]]


def test_engine_sc_vault_not_installed_is_reported(vault: Path, monkeypatch):
    monkeypatch.setattr("granola_sync.sync.indices._sc_vault_installed", lambda: False)
    result = regenerate(_config(vault, engine="sc_vault"), wrote_notes=True)
    assert result.failed and "not installed" in result.reason


def test_engine_auto_prefers_sc_vault(vault: Path, monkeypatch):
    monkeypatch.setattr("granola_sync.sync.indices._sc_vault_installed", lambda: True)
    seen = _capture_cmd(monkeypatch)
    regenerate(_config(vault, engine="auto"), wrote_notes=True)
    assert seen[0][1:3] == ["-m", "sc_vault"]


def test_engine_auto_falls_back_to_the_script(vault: Path, monkeypatch):
    monkeypatch.setattr("granola_sync.sync.indices._sc_vault_installed", lambda: False)
    script = _write_script(vault, "raise SystemExit(0)")
    seen = _capture_cmd(monkeypatch)
    regenerate(_config(vault, engine="auto"), wrote_notes=True)
    assert seen[0][1] == str(script)


def test_unknown_engine_is_reported(vault: Path):
    result = regenerate(_config(vault, engine="magic"), wrote_notes=True)
    assert result.failed and "unknown indices.engine" in result.reason
