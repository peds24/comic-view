"""Command-line entry point for the comic/manga library scanner."""
from __future__ import annotations

import click

from library.config import load_config
from library.enrichment import enrich_all
from library.metadata_sources.google_books import GoogleBooksSource
from library.metadata_sources.metron import MetronSource
from library.scanner import scan_roots
from library.store import load_library, merge_record, save_library


@click.group()
def main() -> None:
    """Scan and enrich a comic/manga library."""


@main.command()
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
def scan(config_path: str) -> None:
    """Recursively scan configured roots and update library.json (no network)."""
    config = load_config(config_path)
    library_path = config.data_dir / "library.json"

    existing = load_library(library_path)
    found, skipped = scan_roots(config)

    added = 0
    for record in found:
        if merge_record(existing, record):
            added += 1

    save_library(library_path, existing)
    click.echo(f"Scanned {len(found)} archive(s). Added {added} new record(s). Total: {len(existing)}.")

    if skipped:
        click.echo(f"Skipped {len(skipped)} unreadable file(s):")
        for path, reason in skipped:
            click.echo(f"  {path}: {reason}")


@main.command()
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--force", is_flag=True, help="Re-query even records that already have all fields.")
def enrich(config_path: str, force: bool) -> None:
    """Fill in missing metadata via Metron and Google Books."""
    config = load_config(config_path)
    library_path = config.data_dir / "library.json"

    records = load_library(library_path)
    if not records:
        click.echo("No records found — run `scan` first.")
        return

    sources = []
    if config.metron.is_configured:
        sources.append(MetronSource(config.metron.username, config.metron.password))
    else:
        click.echo("Metron not configured (skipping) — fill in config.yaml to enable.")
    sources.append(GoogleBooksSource(config.google_books.api_key))

    updated = enrich_all(records, sources, force=force)
    save_library(library_path, records)
    click.echo(f"Enriched {updated} of {len(records)} record(s).")


if __name__ == "__main__":
    main()
