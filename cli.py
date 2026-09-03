"""Command-line entry point for the comic/manga library scanner."""
from __future__ import annotations

import click

from library.config import load_config
from library.enrichment import enrich_all, refetch_physical_covers
from library.excel_importer import import_physical, load_rows
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
    """Fill in missing metadata (and cover images) via Metron and Google Books."""
    config = load_config(config_path)
    library_path = config.data_dir / "library.json"
    covers_dir = config.data_dir / "covers"

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

    updated = enrich_all(records, sources, covers_dir, force=force)
    save_library(library_path, records)
    click.echo(f"Enriched {updated} of {len(records)} record(s).")


@main.command("fetch-covers")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
def fetch_covers_cmd(config_path: str) -> None:
    """Re-fetch covers for every physical-only record, routed by kind: Metron
    for single comic issues, Google Books for manga and TPBs/collected
    editions. Overwrites existing physical-only covers; never touches
    digital or digital+physical records."""
    config = load_config(config_path)
    library_path = config.data_dir / "library.json"
    covers_dir = config.data_dir / "covers"

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

    updated = refetch_physical_covers(records, sources, covers_dir)
    save_library(library_path, records)
    physical_only = sum(1 for r in records.values() if r.formats == ["physical"])
    click.echo(f"Fetched covers for {updated} of {physical_only} physical-only record(s).")


@main.command("import-physical")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--file", "excel_path", required=True, help="Path to a Comic Geeks .xlsx export")
def import_physical_cmd(config_path: str, excel_path: str) -> None:
    """Import physical comics from a Comic Geeks Excel export (no network)."""
    config = load_config(config_path)
    library_path = config.data_dir / "library.json"

    records = load_library(library_path)
    rows = load_rows(excel_path)
    merged, new, skipped = import_physical(records, rows)

    save_library(library_path, records)
    click.echo(
        f"Merged {merged} into existing digital records, added {new} new physical-only "
        f"record(s), skipped {skipped} not-in-collection row(s)."
    )


if __name__ == "__main__":
    main()
