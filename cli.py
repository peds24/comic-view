"""Command-line entry point for the comic/manga library scanner."""
from __future__ import annotations

import functools
import http.server

import click

from library.comic_geeks_importer import import_comic_geeks_xlsx
from library.config import load_config
from library.enrichment import enrich_all, refetch_physical_covers
from library.excel_importer import import_physical, load_rows
from library.metadata_sources.google_books import GoogleBooksSource
from library.metadata_sources.metron import MetronSource
from library.metadata_sources.open_library import OpenLibrarySource
from library.scanner import list_archives, scan_roots
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

    total = len(list_archives(config))
    with click.progressbar(length=total, label="Scanning", show_pos=True) as bar:
        found, skipped = scan_roots(config, on_progress=lambda completed, total: bar.update(1))

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
    """Re-fetch covers for every print-only record, routed by kind: Metron
    for single comic issues, Google Books for manga and TPBs/collected
    editions. Overwrites existing print-only covers; never touches
    digital or digital+print records."""
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
    print_only = sum(1 for r in records.values() if r.formats == ["print"])
    click.echo(f"Fetched covers for {updated} of {print_only} print-only record(s).")


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
        f"Merged {merged} into existing digital records, added {new} new print-only "
        f"record(s), skipped {skipped} not-in-collection row(s)."
    )


@main.command("import-comic-geeks")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--comics", "comics_path", default=None, help="Path to a Comic Geeks comics .xlsx export")
@click.option("--manga", "manga_path", default=None, help="Path to a Comic Geeks manga .xlsx export")
def import_comic_geeks_cmd(config_path: str, comics_path: str | None, manga_path: str | None) -> None:
    """Import comics and/or manga from Comic Geeks exports, enriching each
    row immediately via the source routed by its own UPC/ISBN code: Metron
    for a UPC, Google Books + Open Library for an ISBN, Metron title search
    as a fallback when a row has no usable code."""
    if not comics_path and not manga_path:
        click.echo("Pass --comics and/or --manga.")
        return

    config = load_config(config_path)
    library_path = config.data_dir / "library.json"
    covers_dir = config.data_dir / "covers"

    records = load_library(library_path)

    metron = None
    if config.metron.is_configured:
        metron = MetronSource(config.metron.username, config.metron.password)
    else:
        click.echo("Metron not configured (UPC rows and title-search fallback will be skipped) — fill in config.yaml to enable.")
    google_books = GoogleBooksSource(config.google_books.api_key)
    open_library = OpenLibrarySource()

    for label, path, record_type in (("comics", comics_path, "comic"), ("manga", manga_path, "manga")):
        if not path:
            continue
        stats = import_comic_geeks_xlsx(
            path, record_type, records,
            metron=metron, google_books=google_books, open_library=open_library, covers_dir=covers_dir,
        )
        click.echo(
            f"{label}: added {stats['new']}, skipped {stats['skipped_not_in_collection']} not-in-collection, "
            f"{stats['skipped_corrupted_code']} corrupted code, {stats['skipped_duplicate']} duplicate."
        )

    save_library(library_path, records)
    click.echo(f"Total library size: {len(records)}.")


@main.command()
@click.option("--port", default=8000, help="Port to serve on.")
def serve(port: int) -> None:
    """Serve viewer.html + data/ over HTTP so the browser can fetch
    data/library.json and cover images (opening viewer.html directly via
    file:// blocks those fetches)."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=".")
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        click.echo(f"Serving at http://127.0.0.1:{port}/viewer.html — Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nStopped.")


if __name__ == "__main__":
    main()
