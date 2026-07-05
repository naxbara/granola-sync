"""Main sync orchestration engine.

Supports four modes:
- daily: Sync documents from the last 24h
- historical: Import all documents from a given date
- verify: Check integrity of existing notes
- dry-run: Show what would happen without writing (no detail/enrichment calls)
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
from ..utils import generate_filename
from .dedup import fuzzy_match_title, read_granola_updated, scan_vault_for_granola_ids
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

    @staticmethod
    def _html_to_markdown_basic(html: str) -> str:
        """Convert HTML to markdown (basic conversion for legacy panel content)."""
        import re

        # Remove scripts, styles, and comments
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

        # Convert headings
        for level in range(1, 7):
            text = re.sub(
                rf"<h{level}[^>]*>(.*?)</h{level}>",
                lambda m: f"\n{'#' * level} {m.group(1)}\n",
                text,
                flags=re.DOTALL | re.IGNORECASE,
            )

        # Convert lists
        text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
        text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</?[ou]l[^>]*>", "\n", text, flags=re.IGNORECASE)

        # Convert paragraphs and breaks
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)

        # Convert formatting
        text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)

        # Convert links
        text = re.sub(
            r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
            r"[\2](\1)",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # Remove remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)

        return text.strip()

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
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    def _sync_daily(self) -> None:
        """Sync documents created in the last 24 hours."""
        console.print("Fetching documents from Granola...")
        docs = self.api.get_documents()
        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
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
        console.print(f"Importing documents from {from_date_str}...")

        docs = self.api.get_documents()
        console.print(f"Found {len(docs)} documents total\n")

        self._process_new(docs, keep=lambda d: self._as_utc(d.created_at) >= from_date)

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
                doc.title, date_str, existing_files, self.config.sync.fuzzy_threshold
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
            issue = self._note_integrity_issue(content)
            if issue:
                logger.warning("Integrity issue in %s: %s", file_path.name, issue)
                self.stats.errors += 1
            else:
                self.stats.verified += 1

        console.print(f"Verified {self.stats.verified} notes, {self.stats.errors} issues found")

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
                if is_update:
                    self.stats.updated += 1
                    console.print(f"  [green]~[/green] {label} [dim](dry-run update)[/dim]")
                else:
                    self.stats.new += 1
                    console.print(f"  [green]+[/green] {label} [dim](dry-run)[/dim]")
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
                    md_content = self._html_to_markdown_basic(panel_content)
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

            # 4. Render complete Obsidian note (transcript embedded)
            note_content = render_meeting_note(
                doc, md_content, enrichment, utterances
            )

            # 5. Write to the existing note (update) or a new file (create).
            if is_update:
                write_note_atomic(target_path.parent, target_path.name, note_content)
                self.stats.updated += 1
                console.print(f"  [green]~[/green] {target_path.name}")
            else:
                notes_dir = self.config.vault_path / self.config.sync.notes_folder
                notes_dir.mkdir(exist_ok=True)
                filename = generate_filename(doc.title, date_str)
                write_note_atomic(notes_dir, filename, note_content)
                self.stats.new += 1
                console.print(f"  [green]+[/green] {filename}")

        except Exception as e:
            self.stats.errors += 1
            logger.error("Error processing '%s' (%s): %s", doc.title, doc.id, e)
            console.print(f"  [red]x[/red] {doc.title}: {e}")
