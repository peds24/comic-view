"""Command-line entry point for the comic/manga library scanner."""
from __future__ import annotations

import functools
import http.server

import click

from library.config import load_config
from library.enrichment import enrich_all, refetch_physical_covers
from library.metadata_sources.google_books import GoogleBooksSource
from library.metadata_sources.metron import MetronSource
from library.metadata_sources.open_library import OpenLibrarySource
from library.physical_importer import count_rows, import_physical_xlsx
from library.scanner import list_archives, scan_roots
from library.store import load_library, merge_record, save_library
from library.viewer_server import ViewerRequestHandler


@click.group()
def main() -> None:
    """Scan and enrich a comic/manga library."""


@main.command()
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--data", "data_filename", default="library_digital.json", help="Library JSON filename under data/ to update — scan only ever produces digital-format records.")
def scan(config_path: str, data_filename: str) -> None:
    """Recursively scan configured roots and update the digital library JSON (no network)."""
    config = load_config(config_path)
    library_path = config.data_dir / data_filename

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
@click.option("--file", "excel_path", required=True, help="Path to the physical-collection .xlsx ('comics' and 'manga' sheets)")
def import_physical_cmd(config_path: str, excel_path: str) -> None:
    """Import physical comics/manga from a workbook with 'Comics' (Name,
    UPC/ISBN) and 'Manga' (Name, UPC/ISBN) sheets, enriching each new row
    immediately. A manga row, or a comics row whose code is ISBN-shaped
    (starts with 9 — a collected edition sold under a book ISBN, not a
    single issue's Diamond UPC) goes to Open Library then Google Books;
    everything else goes to Metron."""
    config = load_config(config_path)
    library_path = config.data_dir / "library.json"
    covers_dir = config.data_dir / "covers"

    records = load_library(library_path)

    metron = None
    if config.metron.is_configured:
        metron = MetronSource(config.metron.username, config.metron.password)
    else:
        click.echo("Metron not configured (comics rows will be added without enrichment) — fill in config.yaml to enable.")
    google_books = GoogleBooksSource(config.google_books.api_key)
    open_library = OpenLibrarySource()

    total = count_rows(excel_path)
    with click.progressbar(length=total, label="Importing", show_pos=True) as bar:
        stats = import_physical_xlsx(
            excel_path, records,
            metron=metron, google_books=google_books, open_library=open_library, covers_dir=covers_dir,
            on_progress=lambda completed, total: bar.update(1),
        )

    save_library(library_path, records)
    click.echo(
        f"Comics: added {stats['comics_added']}, merged {stats['comics_merged']} into digital records.\n"
        f"Manga: added {stats['manga_added']}, merged {stats['manga_merged']} into digital records.\n"
        f"Skipped {stats['skipped_corrupted_code']} corrupted code, {stats['skipped_blank_code']} blank code, "
        f"{stats['skipped_duplicate']} duplicate."
    )
    click.echo(f"Total library size: {len(records)}.")


@main.command()
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--port", default=8000, help="Port to serve on.")
@click.option("--data-comics", "comics_filename", default="library_comics.json", help="Comics library JSON filename under data/ to serve.")
@click.option("--data-manga", "manga_filename", default="library_manga.json", help="Manga library JSON filename under data/ to serve.")
def serve(config_path: str, port: int, comics_filename: str, manga_filename: str) -> None:
    """Serve viewer.html + data/ over HTTP so the browser can fetch
    data/library.json and cover images (opening viewer.html directly via
    file:// blocks those fetches). Also exposes the write endpoints
    viewer.html's per-card controls use to manually attach a cover image,
    attach a Comic Geeks link, edit a title/year/formats, or delete a
    record. GET /data/library.json merges the comics and manga files
    transparently — viewer.html doesn't know the library is split."""
    config = load_config(config_path)
    comics_path = config.data_dir / comics_filename
    manga_path = config.data_dir / manga_filename
    covers_dir = config.data_dir / "covers"

    handler = functools.partial(
        ViewerRequestHandler, directory=".", comics_path=comics_path, manga_path=manga_path,
        covers_dir=covers_dir, config=config,
    )
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        click.echo(f"Serving at http://127.0.0.1:{port}/viewer.html — Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nStopped.")


if __name__ == "__main__":
    main()
