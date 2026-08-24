"""Turn a suggested speaker name into a confirmed one.

The sync never renames a speaker on its own: when it has a hunch it writes the
candidates into the transcript's frontmatter and leaves the body saying
"Speaker". This module is where a human settles it, either by answering the
prompts here or by typing ``speaker_confirmed:`` into the note in Obsidian —
both land in the same place, and this applies whichever it finds.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from rich.console import Console

from ..converters.speakers import (
    ATTRIBUTION_CONFIRMED,
    ATTRIBUTION_SUGGESTED,
    GENERIC_LABEL,
)

logger = logging.getLogger(__name__)
console = Console()

# Only the closing delimiter's own line ending is consumed: a greedy \s* here
# would swallow the blank line that follows and quietly reformat the note.
FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n", re.S)
SPOKEN_LINE = re.compile(r"^(\*\*\[[\d:]+\]\*\* _)([^_]+)(_: )", re.M)
# Frontmatter keys this module owns; rewritten wholesale on each application.
OWNED_KEYS = (
    "speaker_attribution",
    "speaker_confirmed",
    "speaker_candidates",
    "speaker_evidence",
)


def read_frontmatter(path: Path) -> dict:
    """Parse a transcript's frontmatter, or an empty dict if unreadable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        logger.debug("Unreadable frontmatter in %s", path.name)
        return {}
    return data if isinstance(data, dict) else {}


def confirmed_speaker(path: Path) -> str | None:
    """The name already settled for this transcript, if any.

    The sync calls this before regenerating a transcript so that answering the
    question once survives every later resync.
    """
    value = read_frontmatter(path).get("speaker_confirmed")
    return str(value).strip() or None if value else None


def apply_confirmation(path: Path, name: str) -> int:
    """Relabel the generic turns in a transcript and record the decision.

    Only turns that still carry the generic label are touched: "You" is the
    mic owner and stays, and a name Granola itself attributed is better data
    than ours. Returns how many lines changed.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    match = FRONTMATTER.match(text)
    if not match:
        raise ValueError(f"{path.name} has no frontmatter")

    kept = [
        line
        for line in match.group(1).split("\n")
        if not line.startswith(tuple(f"{key}:" for key in OWNED_KEYS))
    ]
    kept.append(f"speaker_attribution: {ATTRIBUTION_CONFIRMED}")
    kept.append(f"speaker_confirmed: {name}")

    body = text[match.end() :]
    changed = 0

    def relabel(m: re.Match[str]) -> str:
        nonlocal changed
        if m.group(2) != GENERIC_LABEL:
            return m.group(0)
        changed += 1
        return f"{m.group(1)}{name}{m.group(3)}"

    body = SPOKEN_LINE.sub(relabel, body)
    path.write_text("---\n" + "\n".join(kept) + "\n---\n" + body, encoding="utf-8")
    return changed


def _pending(transcripts_dir: Path) -> list[tuple[Path, dict]]:
    """Transcripts waiting on a decision, newest first.

    Two kinds qualify: ones the sync flagged as suggestions, and ones where a
    name was typed into the note by hand but never applied to the body.
    """
    found = []
    for path in sorted(transcripts_dir.glob("*.md"), reverse=True):
        meta = read_frontmatter(path)
        attribution = meta.get("speaker_attribution")
        if attribution == ATTRIBUTION_CONFIRMED:
            continue
        if attribution == ATTRIBUTION_SUGGESTED or meta.get("speaker_confirmed"):
            found.append((path, meta))
    return found


def _sample_lines(path: Path, limit: int = 3) -> list[str]:
    """A few of the other side's actual words, to jog the memory."""
    text = path.read_text(encoding="utf-8", errors="replace")
    spoken = [
        line
        for line in text.split("\n")
        if f"_{GENERIC_LABEL}_:" in line and len(line) > 60
    ]
    return spoken[:limit]


def run(transcripts_dir: Path) -> int:
    """Walk the pending transcripts and ask. Returns how many were settled."""
    if not transcripts_dir.is_dir():
        console.print(f"[yellow]No transcripts folder at {transcripts_dir}[/yellow]")
        return 0

    pending = _pending(transcripts_dir)
    if not pending:
        console.print("[green]Nothing pending[/green] - every transcript is settled.")
        return 0

    console.print(f"\n[bold]{len(pending)}[/bold] transcript(s) waiting on a name.")
    console.print("[dim]number = pick | text = another name | enter = skip | q = quit[/dim]\n")

    settled = 0
    for path, meta in pending:
        # Typed into the note by hand: nothing to ask, just apply it.
        already = meta.get("speaker_confirmed")
        if already:
            changed = apply_confirmation(path, str(already).strip())
            console.print(f"[green]+[/green] {path.stem} -> {already} ({changed} lines)")
            settled += 1
            continue

        candidates = meta.get("speaker_candidates") or []
        if isinstance(candidates, str):
            candidates = [c.strip() for c in candidates.strip("[]").split(",") if c.strip()]

        console.print(f"[bold cyan]{path.stem}[/bold cyan]")
        if meta.get("speaker_evidence"):
            console.print(f"  [dim]{meta['speaker_evidence']}[/dim]")
        for line in _sample_lines(path):
            console.print(f"  [dim]{line[:110]}[/dim]")
        for index, name in enumerate(candidates, start=1):
            console.print(f"  [bold]{index}[/bold]) {name}")

        try:
            answer = input("  ¿Quién habla? ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Interrupted[/yellow]")
            break

        if answer.lower() == "q":
            break
        if not answer:
            console.print("  [dim]skipped[/dim]\n")
            continue

        chosen = answer
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            chosen = str(candidates[int(answer) - 1])

        changed = apply_confirmation(path, chosen)
        console.print(f"  [green]+[/green] {chosen} ({changed} lines)\n")
        settled += 1

    console.print(f"\n[bold]{settled}[/bold] settled, {len(pending) - settled} left.")
    return settled
