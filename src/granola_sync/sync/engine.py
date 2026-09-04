"""Main sync orchestration engine.

Supports four modes:
- daily: Sync documents from the last 24h
- historical: Import all documents from a given date
- verify: Check integrity of existing notes
- dry-run: Show what would happen without writing (no detail/enrichment calls)
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from ..api.models import GranolaDocument
from ..converters import people
from ..converters.html import html_to_markdown
from ..converters.people import PersonasIndex
from ..converters.prosemirror import ProseMirrorToMarkdown
from ..converters.speakers import suggest_speakers
from ..converters.template import render_meeting_note
from ..converters.transcript import render_transcript_note, transcript_filename
from ..sources.calendar import CalendarLookup
from ..utils import generate_filename
from .dedup import fuzzy_match_title, read_granola_updated, scan_vault_for_granola_ids
from .speaker_confirm import confirmed_speaker
from .vault import write_note_atomic

if TYPE_CHECKING:
    from pathlib import Path

    from ..api.client import GranolaAPIClient
    from ..config import AppConfig
    from ..enrichment.claude_enricher import ClaudeEnricher

logger = logging.getLogger(__name__)
console = Console()


class SyncStats:
    """Track sync operation statistics."""

    def __init__(self) -> None:
        self.new = 0
        self.updated = 0
        self.skipped = 0
        self.errors = 0
        self.verified = 0

    def print_summary(self) -> None:
        table = Table(title="Sync Summary")
        table.add_column("Metric", style="bold")
        table.add_column("Count", justify="right")
        table.add_row("New notes", str(self.new), style="green")
        table.add_row("Updated notes", str(self.updated), style="green")
        table.add_row("Skipped (duplicates)", str(self.skipped), style="yellow")
        table.add_row("Verified", str(self.verified), style="blue")
        table.add_row("Errors", str(self.errors), style="red" if self.errors else "dim")
        console.print(table)


class SyncEngine:
    """Orchestrates the sync between Granola and Obsidian."""

    def __init__(
        self,
        config: AppConfig,
        api: GranolaAPIClient,
        enricher: ClaudeEnricher | None = None,
    ) -> None:
        self.config = config
        self.api = api
        self.enricher = enricher
        self.converter = ProseMirrorToMarkdown()
        self.stats = SyncStats()
        # Participant sources are built on first use: dry-run must not
        # authenticate against Calendar or walk the vault for nothing.
        self._personas: PersonasIndex | None = None
        self._calendar = None
        self._calendar_ready = False

    def _participants(self, doc: GranolaDocument) -> list[people.Participant]:
        """Who attended, from Granola, then Calendar, then the vault."""
        if self._personas is None:
            self._personas = PersonasIndex.from_vault(self.config.vault_path)
            logger.debug("Indexed %d addresses from Personas/", len(self._personas))

        if not self._calendar_ready:
            self._calendar = CalendarLookup.build(self.config)
            self._calendar_ready = True
            if self._calendar:
                console.print("[dim]Google Calendar lookup enabled[/dim]")

        calendar_emails = None
        if self._calendar:
            calendar_emails = self._calendar.emails_for(doc.title, doc.meeting_date)

        return people.resolve(doc, calendar_emails, self._personas)

    def _owner_names(self) -> set[str]:
        """What the vault calls the owner, so suggestions skip their own name.

        It shows up in every transcript — people say "Sebastián" constantly —
        and would otherwise be the loudest candidate in the room.
        """
        names = set()
        for email in self.config.owner_emails:
            known = self._personas.enrich([people.Participant(email=email)])[0]
            if known.name:
                names.add(known.name)
        return names

    def _speaker_candidates(self, doc: GranolaDocument, utterances) -> list:
        """Names from the vault that the title and the transcript both mention."""
        if not utterances or self._personas is None:
            return []
        return suggest_speakers(
            doc.title, utterances, self._personas, self._owner_names()
        )

    def run(self) -> SyncStats:
        """Execute sync based on the configured mode."""
        mode = self.config.mode
        console.print(f"\n[bold]Granola Sync[/bold] — mode: [cyan]{mode}[/cyan]")

        if self.config.dry_run:
            console.print("[yellow]DRY RUN — no files will be written[/yellow]\n")

        match mode:
            case "daily":
                self._sync_daily()
            case "historical":
                self._sync_historical()
            case "verify":
                self._verify()
            case "dry-run":
                self.config.dry_run = True
                self._sync_daily()
            case _:
                logger.error("Unknown sync mode: %s", mode)

        self.stats.print_summary()
        return self.stats

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        """Normalize a datetime to UTC without overwriting an existing tzinfo."""
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

    def _sync_daily(self) -> None:
        """Sync documents created in the last 24 hours."""
        console.print("Fetching documents from Granola...")
        docs = self.api.get_documents()
        cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
        id_map = scan_vault_for_granola_ids(self.config.vault_path)
        console.print(f"Found {len(docs)} documents, {len(id_map)} already synced\n")

        self._process_new(docs, keep=lambda d: self._as_utc(d.created_at) >= cutoff_24h)

    def _sync_historical(self) -> None:
        """Import all documents from a given date."""
        from_date_str = self.config.from_date
        if not from_date_str:
            logger.error("Historical mode requires --from date")
            return

        from_date = self._as_utc(datetime.fromisoformat(from_date_str))

        # Optional inclusive end date: keep anything strictly before the next day.
        to_date_excl = None
        if self.config.to_date:
            to_date_excl = self._as_utc(datetime.fromisoformat(self.config.to_date)) + timedelta(days=1)

        window = from_date_str + (f" to {self.config.to_date}" if self.config.to_date else " onward")
        console.print(f"Importing documents from {window}...")

        docs = self.api.get_documents()
        console.print(f"Found {len(docs)} documents total\n")

        def keep(d: GranolaDocument) -> bool:
            created = self._as_utc(d.created_at)
            if created < from_date:
                return False
            if to_date_excl is not None and created >= to_date_excl:
                return False
            return True

        self._process_new(docs, keep=keep)

    def _process_new(self, docs, keep) -> None:
        """Filter docs in the date window, batch-hydrate, and create/update notes.

        ``keep`` selects docs in the mode's date window. A doc already in the
        vault is regenerated only when its source ``updated_at`` is newer than
        the note's stored ``granola_updated``; otherwise it is skipped. Fresh
        docs are created. Full content is hydrated in as few batch requests as
        possible (skipped entirely in dry-run).
        """
        id_map = scan_vault_for_granola_ids(self.config.vault_path)
        notes_dir = self.config.vault_path / self.config.sync.notes_folder
        existing_files = list(notes_dir.glob("*.md")) if notes_dir.exists() else []
        # A note that already carries a granola_id belongs to some other
        # meeting — the same doc would have been caught by the id lookup below.
        # Letting those into the fuzzy pass is what made a second meeting of
        # the same day ("... v2") look like a duplicate of the first one, so
        # the fuzzy fallback only ever sees hand-written or pre-id notes.
        claimed = set(id_map.values())
        unclaimed_files = [fp for fp in existing_files if fp not in claimed]

        to_create: list[GranolaDocument] = []
        to_update: list[tuple[GranolaDocument, Path]] = []
        for doc in docs:
            if doc.deleted_at:
                continue
            if not keep(doc):
                self.stats.skipped += 1
                continue

            # Already synced: regenerate only if the source changed since.
            if doc.id in id_map:
                existing = id_map[doc.id]
                stored = read_granola_updated(existing)
                if stored is not None and self._as_utc(doc.updated_at) > stored:
                    to_update.append((doc, existing))
                    logger.info("Update queued (changed since sync): %s", doc.title)
                else:
                    self.stats.skipped += 1
                continue

            date_str = doc.meeting_date.strftime("%Y-%m-%d")
            if fuzzy_match_title(
                doc.title, date_str, unclaimed_files, self.config.sync.fuzzy_threshold
            ):
                self.stats.skipped += 1
                logger.info("Skipped (fuzzy match): %s", doc.title)
                continue
            to_create.append(doc)

        # Hydrate full content for all new/changed docs at once. Dry-run stays
        # free — no detail fetch, no transcript, no enrichment (see below).
        full_map: dict[str, GranolaDocument] = {}
        if (to_create or to_update) and not self.config.dry_run:
            ids = [d.id for d in to_create] + [d.id for d, _ in to_update]
            try:
                full = self.api.get_documents_batch(ids)
                full_map = {d.id: d for d in full}
            except Exception as e:
                logger.warning("Batch hydrate failed, using list data: %s", e)

        for doc in to_create:
            self._process_document(full_map.get(doc.id, doc))
        for doc, path in to_update:
            self._process_document(full_map.get(doc.id, doc), target_path=path)

    def _verify(self) -> None:
        """Verify integrity of existing synced notes."""
        id_map = scan_vault_for_granola_ids(self.config.vault_path)
        console.print(f"Verifying {len(id_map)} synced notes...")

        for granola_id, file_path in id_map.items():
            if not file_path.exists():
                logger.warning("Missing file for granola_id %s: %s", granola_id, file_path)
                self.stats.errors += 1
                continue

            content = file_path.read_text(encoding="utf-8")
            issue = self._note_integrity_issue(content) or self._missing_transcript(content)
            if issue:
                logger.warning("Integrity issue in %s: %s", file_path.name, issue)
                self.stats.errors += 1
            else:
                self.stats.verified += 1

        console.print(f"Verified {self.stats.verified} notes, {self.stats.errors} issues found")

    def _missing_transcript(self, content: str) -> str | None:
        """Return an issue when the callout links to a transcript that is gone.

        Notes written in "separate" mode point at Transcripciones/; a broken
        link there means the transcript was lost, which the body check above
        cannot see.
        """
        match = re.search(r"^> Ver: \[\[([^\]]+)\]\]", content, re.M)
        if not match:
            return None
        target = (
            self.config.vault_path
            / self.config.sync.transcripts_folder
            / f"{match.group(1)}.md"
        )
        if not target.exists():
            return f"linked transcript not found: {target.name}"
        return None

    @staticmethod
    def _note_integrity_issue(content: str) -> str | None:
        """Return a short description of the note's integrity problem, or None.

        A note is healthy when it has a frontmatter block containing granola_id
        and a non-empty body after the frontmatter (frontmatter alone easily
        exceeds a naive length threshold, so we check the body explicitly).
        """
        if not content.startswith("---"):
            return "missing frontmatter"
        end = content.find("---", 3)
        if end == -1:
            return "unterminated frontmatter"
        if "granola_id" not in content[3:end]:
            return "frontmatter missing granola_id"
        body = content[end + 3:].strip()
        if not body:
            return "empty body"
        return None

    def _process_document(
        self, doc: GranolaDocument, target_path: Path | None = None
    ) -> None:
        """Convert and write a single document to the vault.

        When ``target_path`` is given the note is regenerated in place (an
        update); otherwise a new file is created. In dry-run we only report
        what would happen — no transcript fetch and no Claude enrichment
        (both cost API calls / money).
        """
        is_update = target_path is not None
        try:
            date_str = doc.meeting_date.strftime("%Y-%m-%d")

            # Dry-run: report the would-be action without any paid/detail work.
            if self.config.dry_run:
                label = target_path.name if is_update else generate_filename(doc.title, date_str)
                # Dry-run never fetches the transcript, so we can only report
                # what the configuration would produce, not whether one exists.
                pair = (
                    ", note + transcript"
                    if self.config.sync.transcript_mode == "separate"
                    and self.config.sync.include_transcripts
                    else ""
                )
                if is_update:
                    self.stats.updated += 1
                    console.print(
                        f"  [green]~[/green] {label} [dim](dry-run update{pair})[/dim]"
                    )
                else:
                    self.stats.new += 1
                    console.print(f"  [green]+[/green] {label} [dim](dry-run{pair})[/dim]")
                return

            # 1. Extract content — priority: last_viewed_panel (AI summary) > notes > panels > overview
            md_content = ""

            # The AI-generated summary lives in last_viewed_panel.content
            # Can be ProseMirror JSON (dict) or HTML string (legacy format)
            if doc.last_viewed_panel and doc.last_viewed_panel.content:
                panel_content = doc.last_viewed_panel.content
                if isinstance(panel_content, dict):
                    md_content = self.converter.convert(panel_content)
                    if md_content.strip():
                        logger.debug("Using last_viewed_panel ProseMirror content for '%s'", doc.title)
                elif isinstance(panel_content, str):
                    # HTML content (legacy) — convert to markdown
                    md_content = html_to_markdown(panel_content)
                    if md_content.strip():
                        logger.debug("Using last_viewed_panel HTML content for '%s'", doc.title)

            # Fallback: user's raw notes (ProseMirror JSON)
            if not md_content.strip():
                if doc.notes and isinstance(doc.notes, dict):
                    md_content = self.converter.convert(doc.notes)
                elif doc.notes_markdown:
                    md_content = doc.notes_markdown or ""
                elif doc.notes_plain:
                    md_content = doc.notes_plain or ""

            # Fallback: other panels
            if not md_content.strip() and doc.panels:
                for panel in doc.panels:
                    if panel.content and isinstance(panel.content, dict):
                        panel_md = self.converter.convert(panel.content)
                        if panel_md.strip():
                            md_content = panel_md
                            break

            # Fallback: overview or summary text
            if not md_content.strip() and doc.overview:
                md_content = doc.overview
            if not md_content.strip() and doc.summary:
                md_content = doc.summary

            # 2. Fetch transcript (if enabled)
            utterances = None
            if self.config.sync.include_transcripts:
                try:
                    utterances = self.api.get_transcript(doc.id)
                except Exception as e:
                    logger.warning("Failed to fetch transcript for '%s': %s", doc.title, e)

            # 3. AI enrichment
            enrichment = None
            if self.enricher and not self.config.no_enrich:
                enrichment = self.enricher.enrich(doc.title, md_content)

            # 4. Resolve where the note goes. The transcript is paired with it
            #    by filename stem, so an update keeps both files together even
            #    if the meeting title changed upstream.
            if is_update:
                notes_dir = target_path.parent
                filename = target_path.name
            else:
                notes_dir = self.config.vault_path / self.config.sync.notes_folder
                filename = generate_filename(doc.title, date_str)
            note_stem = filename[:-3] if filename.endswith(".md") else filename

            mode = self.config.sync.transcript_mode
            separate = mode == "separate" and bool(utterances)

            # 5. Resolve who attended, then render the note (and its
            #    standalone transcript, if separate).
            attendees = self._participants(doc)
            note_content = render_meeting_note(
                doc,
                md_content,
                enrichment,
                utterances,
                transcript_mode=mode,
                note_stem=note_stem,
                participants=attendees,
            )

            # 6. Write the transcript first: the note links to it, so it should
            #    never point at a file that does not exist yet.
            if separate:
                transcripts_dir = (
                    self.config.vault_path / self.config.sync.transcripts_folder
                )
                transcripts_dir.mkdir(parents=True, exist_ok=True)
                transcript_name = transcript_filename(note_stem)
                # A name the user already settled outlives a regeneration:
                # answering the question once has to be enough.
                settled = confirmed_speaker(transcripts_dir / transcript_name)
                write_note_atomic(
                    transcripts_dir,
                    transcript_name,
                    render_transcript_note(
                        doc,
                        date_str,
                        attendees,
                        utterances,
                        note_stem,
                        owner_emails=set(self.config.owner_emails),
                        candidates=None if settled else self._speaker_candidates(doc, utterances),
                        confirmed_speaker=settled,
                    ),
                )

            notes_dir.mkdir(parents=True, exist_ok=True)
            write_note_atomic(notes_dir, filename, note_content)

            suffix = " [dim](+ transcript)[/dim]" if separate else ""
            if is_update:
                self.stats.updated += 1
                console.print(f"  [green]~[/green] {filename}{suffix}")
            else:
                self.stats.new += 1
                console.print(f"  [green]+[/green] {filename}{suffix}")

        except Exception as e:
            self.stats.errors += 1
            logger.error("Error processing '%s' (%s): %s", doc.title, doc.id, e)
            console.print(f"  [red]x[/red] {doc.title}: {e}")
