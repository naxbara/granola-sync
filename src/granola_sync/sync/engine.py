"""Main sync orchestration engine.

Supports four modes:
- daily: Sync last 24h + verify last 2 weeks
- historical: Import all documents from a given date
- verify: Check integrity of existing notes
- dry-run: Show what would happen without writing
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from ..api.models import GranolaDocument
from ..converters.prosemirror import ProseMirrorToMarkdown
from ..converters.template import render_meeting_note
from ..converters.transcript import format_transcript
from ..utils import generate_filename
from .dedup import fuzzy_match_title, scan_vault_for_granola_ids
from .vault import write_note_atomic

if TYPE_CHECKING:
    from ..api.client import GranolaAPIClient
    from ..config import AppConfig
    from ..enrichment.claude_enricher import ClaudeEnricher

logger = logging.getLogger(__name__)
console = Console()


class SyncStats:
    """Track sync operation statistics."""

    def __init__(self) -> None:
        self.new = 0
        self.skipped = 0
        self.errors = 0
        self.verified = 0

    def print_summary(self) -> None:
        table = Table(title="Sync Summary")
        table.add_column("Metric", style="bold")
        table.add_column("Count", justify="right")
        table.add_row("New notes", str(self.new), style="green")
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

    def _sync_daily(self) -> None:
        """Sync last 24 hours + verify documents from last 2 weeks."""
        console.print("Fetching documents from Granola...")
        docs = self.api.get_documents()
        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)

        # Build index of existing notes
        id_map = scan_vault_for_granola_ids(self.config.vault_path)
        existing_files = list(self.config.vault_path.glob("*.md"))

        console.print(f"Found {len(docs)} documents, {len(id_map)} already synced\n")

        for doc in docs:
            if doc.deleted_at:
                continue

            # Check for existing by granola_id
            if doc.id in id_map:
                self.stats.skipped += 1
                continue

            # Check for existing by fuzzy title match
            date_str = doc.meeting_date.strftime("%Y-%m-%d")
            if fuzzy_match_title(
                doc.title,
                date_str,
                existing_files,
                self.config.sync.fuzzy_threshold,
            ):
                self.stats.skipped += 1
                logger.info("Skipped (fuzzy match): %s", doc.title)
                continue

            # Only process documents from last 24h in daily mode
            if doc.created_at.replace(tzinfo=timezone.utc) < cutoff_24h:
                self.stats.skipped += 1
                continue

            self._process_document(doc)

    def _sync_historical(self) -> None:
        """Import all documents from a given date."""
        from_date_str = self.config.from_date
        if not from_date_str:
            logger.error("Historical mode requires --from date")
            return

        from_date = datetime.fromisoformat(from_date_str).replace(tzinfo=timezone.utc)
        console.print(f"Importing documents from {from_date_str}...")

        docs = self.api.get_documents()
        id_map = scan_vault_for_granola_ids(self.config.vault_path)
        existing_files = list(self.config.vault_path.glob("*.md"))

        console.print(f"Found {len(docs)} documents total\n")

        for doc in docs:
            if doc.deleted_at:
                continue

            doc_created = doc.created_at
            if doc_created.tzinfo is None:
                doc_created = doc_created.replace(tzinfo=timezone.utc)

            if doc_created < from_date:
                continue

            if doc.id in id_map:
                self.stats.skipped += 1
                continue

            date_str = doc.meeting_date.strftime("%Y-%m-%d")
            if fuzzy_match_title(
                doc.title, date_str, existing_files, self.config.sync.fuzzy_threshold
            ):
                self.stats.skipped += 1
                continue

            self._process_document(doc)

    def _verify(self) -> None:
        """Verify integrity of existing synced notes."""
        id_map = scan_vault_for_granola_ids(self.config.vault_path)
        console.print(f"Verifying {len(id_map)} synced notes...")

        for granola_id, file_path in id_map.items():
            if not file_path.exists():
                logger.warning("Missing file for granola_id %s: %s", granola_id, file_path)
                self.stats.errors += 1
            else:
                content = file_path.read_text(encoding="utf-8")
                if len(content) < 50:
                    logger.warning("Suspiciously short note: %s (%d chars)", file_path.name, len(content))
                    self.stats.errors += 1
                else:
                    self.stats.verified += 1

        console.print(f"Verified {self.stats.verified} notes, {self.stats.errors} issues found")

    def _process_document(self, doc: GranolaDocument) -> None:
        """Convert and write a single document to the vault."""
        try:
            # 1. Convert ProseMirror notes to Markdown
            md_content = ""
            if doc.notes and isinstance(doc.notes, dict):
                md_content = self.converter.convert(doc.notes)
            elif doc.notes_markdown:
                md_content = doc.notes_markdown or ""
            elif doc.notes_plain:
                md_content = doc.notes_plain or ""

            # Also check panels for content
            if not md_content and doc.panels:
                for panel in doc.panels:
                    if panel.content and isinstance(panel.content, dict):
                        panel_md = self.converter.convert(panel.content)
                        if panel_md:
                            md_content = panel_md
                            break

            date_str = doc.meeting_date.strftime("%Y-%m-%d")

            # 2. Fetch and write transcript (if enabled)
            transcript_filename = None
            if self.config.sync.include_transcripts:
                try:
                    utterances = self.api.get_transcript(doc.id)
                    if utterances:
                        transcript_filename = generate_filename(
                            doc.title, date_str, suffix="-transcript"
                        )
                        transcript_md = format_transcript(utterances, doc.title)
                        if not self.config.dry_run:
                            write_note_atomic(
                                self.config.vault_path,
                                transcript_filename,
                                transcript_md,
                            )
                        logger.info("Transcript: %s", transcript_filename)
                except Exception as e:
                    logger.warning("Failed to fetch transcript for '%s': %s", doc.title, e)

            # 3. AI enrichment
            enrichment = None
            if self.enricher and not self.config.no_enrich:
                enrichment = self.enricher.enrich(doc.title, md_content)

            # 4. Render complete Obsidian note
            note_content = render_meeting_note(
                doc, md_content, enrichment, transcript_filename
            )

            # 5. Write to vault
            filename = generate_filename(doc.title, date_str)
            if not self.config.dry_run:
                write_note_atomic(self.config.vault_path, filename, note_content)

            self.stats.new += 1
            console.print(f"  [green]+[/green] {filename}")

        except Exception as e:
            self.stats.errors += 1
            logger.error("Error processing '%s' (%s): %s", doc.title, doc.id, e)
            console.print(f"  [red]x[/red] {doc.title}: {e}")
