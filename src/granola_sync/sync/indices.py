"""Regenerate the vault's derived indexes after a sync wrote notes.

The vault keeps four generated indexes in `Indices/` — meetings by client, by
person, a timeline, and the decision log — built entirely from the frontmatter
this sync writes. A new meeting note makes them stale immediately, so the
cheapest place to refresh them is right here: when the source changed, not on a
clock that fires whether anything happened or not.

Two rules shape this module:

1. **It never fails the sync.** The notes are the product; the indexes are
   derived and can be rebuilt by hand at any time. A missing script, a crash or
   a timeout is reported and the sync still exits successfully.
2. **It only runs when something changed.** No new or updated notes, or a
   dry-run, means the indexes already match the vault.
"""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class IndicesResult:
    """Outcome of the attempt, for the caller to report."""

    ran: bool
    ok: bool = False
    reason: str = ""

    @property
    def failed(self) -> bool:
        return self.ran and not self.ok


def _resolve_script(vault_path: Path, script: str) -> Path:
    candidate = Path(script).expanduser()
    return candidate if candidate.is_absolute() else vault_path / candidate


def _sc_vault_installed() -> bool:
    return importlib.util.find_spec("sc_vault") is not None


def _command(config) -> tuple[list[str] | None, str]:
    """The generator command for `indices.engine`, or (None, why it cannot run)."""
    engine = (config.indices.engine or "script").lower()
    if engine not in ("script", "sc_vault", "auto"):
        return None, f"unknown indices.engine: {engine!r} (use script, sc_vault or auto)"
    vault = str(config.vault_path)
    if engine == "sc_vault" or (engine == "auto" and _sc_vault_installed()):
        if not _sc_vault_installed():
            return None, "indices.engine is sc_vault but sc_vault is not installed"
        return [sys.executable, "-m", "sc_vault", "indices", "--vault", vault, "--apply"], ""
    script = _resolve_script(config.vault_path, config.indices.script)
    if not script.is_file():
        return None, f"index generator not found: {script}"
    return [sys.executable, str(script), "--vault", vault, "--apply"], ""


def regenerate(config, wrote_notes: bool) -> IndicesResult:
    """Run the index generator. Returns what happened; never raises."""
    if not config.indices.enabled:
        return IndicesResult(ran=False, reason="disabled in config")

    if config.dry_run:
        return IndicesResult(ran=False, reason="dry-run")

    if not wrote_notes:
        return IndicesResult(ran=False, reason="no notes written")

    cmd, why_not = _command(config)
    if cmd is None:
        logger.warning(why_not)
        return IndicesResult(ran=True, ok=False, reason=why_not)

    logger.info("Regenerating vault indexes: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.indices.timeout_seconds,
            cwd=str(config.vault_path),
            check=False,
        )
    except subprocess.TimeoutExpired:
        msg = f"index generator timed out after {config.indices.timeout_seconds}s"
        logger.warning(msg)
        return IndicesResult(ran=True, ok=False, reason=msg)
    except OSError as e:
        msg = f"could not run index generator: {e}"
        logger.warning(msg)
        return IndicesResult(ran=True, ok=False, reason=msg)

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit code {proc.returncode}"
        msg = f"index generator failed: {tail}"
        logger.warning("%s\n%s", msg, proc.stderr)
        return IndicesResult(ran=True, ok=False, reason=msg)

    logger.info("Vault indexes regenerated")
    return IndicesResult(ran=True, ok=True)
