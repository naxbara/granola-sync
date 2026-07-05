"""Command-line interface for Granola-to-Obsidian sync."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from rich.console import Console

console = Console()


def main() -> None:
    """Entry point for the granola-sync CLI."""
    parser = argparse.ArgumentParser(
        description="Sync Granola meeting notes to Obsidian vault",
        prog="granola-sync",
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "historical", "verify", "dry-run"],
        default="daily",
        help="Sync mode (default: daily)",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        type=str,
        default=None,
        help="Start date for historical mode (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        type=str,
        default=None,
        help="End date for historical mode (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help="Override Obsidian vault path",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip Claude AI enrichment",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Load config
    from .config import AppConfig
    from .logging_config import setup_logging

    if args.config.exists():
        config = AppConfig.from_yaml(args.config)
    else:
        console.print(f"[yellow]Config file not found: {args.config}[/yellow]")
        console.print("Using defaults. Copy config.example.yaml to config.yaml to customize.\n")
        config = AppConfig()

    # Apply CLI overrides
    config.mode = args.mode
    config.from_date = args.from_date
    config.to_date = args.to_date
    config.no_enrich = args.no_enrich
    config.dry_run = args.mode == "dry-run"

    if args.vault:
        config.vault_path = args.vault.expanduser()

    if args.verbose:
        config.logging.verbose = True

    # Anchor a relative log dir to the config file's directory (deterministic
    # regardless of the CWD the process was launched from), not the CWD.
    base_dir = args.config.resolve().parent if args.config.exists() else Path.cwd()
    log_dir = Path(config.logging.dir)
    if not log_dir.is_absolute():
        log_dir = base_dir / log_dir

    # Setup logging
    log_file = setup_logging(
        log_dir=str(log_dir),
        verbose=config.logging.verbose,
    )

    # Validate config
    errors = config.validate()
    if errors:
        for err in errors:
            console.print(f"[red]Config error:[/red] {err}")
        sys.exit(1)

    # Initialize components
    from .api.client import GranolaAPIClient
    from .auth.token_manager import TokenManager
    from .enrichment.claude_enricher import ClaudeEnricher
    from .sync.engine import SyncEngine

    try:
        token_manager = TokenManager(config.credentials_path, config.workos_client_id)
        api_client = GranolaAPIClient(token_manager)

        enricher = None
        if config.enrichment.enabled and not config.no_enrich:
            enricher = ClaudeEnricher(
                api_key=config.enrichment.api_key,
                model=config.enrichment.model,
            )
            console.print("[dim]Claude AI enrichment enabled[/dim]")

        engine = SyncEngine(config, api_client, enricher)
        stats = engine.run()

        console.print(f"\n[dim]Log file: {log_file}[/dim]")

        # Exit with error code if there were errors
        if stats.errors > 0:
            sys.exit(1)

    except FileNotFoundError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        console.print("Make sure the Granola app is installed and you've logged in at least once.")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        console.print(
            f"\n[red]Error:[/red] Granola API returned {e.response.status_code} for "
            f"{e.request.url}. If this is 401, re-authenticate in the Granola app."
        )
        sys.exit(1)
    except httpx.RequestError as e:
        console.print(f"\n[red]Error:[/red] Could not reach the Granola API: {e}")
        console.print("Check your internet connection and try again.")
        sys.exit(1)
    except RuntimeError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)
    finally:
        if "api_client" in locals():
            api_client.close()
