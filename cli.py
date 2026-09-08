"""Command-line entry point for the comic/manga library scanner."""
from __future__ import annotations

import functools
import http.server
from datetime import date

import click

from library.config import load_config
from library.covers import download_cover
from library.enrichment import enrich_all, refetch_physical_covers
from library.git_utils import commit_if_changed
from library.matching import find_matching_record, is_matchable
from library.metadata_sources import comic_geeks
from library.metadata_sources.google_books import GoogleBooksSource
from library.metadata_sources.metron import MetronSource
from library.metadata_sources.open_library import OpenLibrarySource
from library.models import ComicRecord
from library.physical_importer import count_rows, import_physical_xlsx
from library.pull_calendar import fetch_pulled_items, load_state, save_state
from library.pull_resolver import ResolveResult, resolve_and_add
from library.scanner import list_archives, scan_roots
from library.sheets_sync import sync_comics_to_sheet
from library.store import load_library, merge_record, save_library
from library.viewer_server import ViewerRequestHandler


@click.group()
def main() -> None:
    """Scan and enrich a comic/manga library."""


_DESCRIPTION_PREVIEW_LIMIT = 200


def _echo_comic_preview(*, title: str, year, author, description) -> None:
    """Prints one comic's title/year/author/description for a
    confirmation prompt — used by both check-pulls (previewing a
    resolved ComicRecord) and add-comic (previewing the raw fetched
    Comic Geeks info) so the two share one formatting/truncation rule."""
    click.echo(f"  - {title}")
    click.echo(f"      Published: {year or 'unknown'}")
    click.echo(f"      Author: {author or 'unknown'}")
    desc = (description or "").strip()
    if len(desc) > _DESCRIPTION_PREVIEW_LIMIT:
        desc = desc[:_DESCRIPTION_PREVIEW_LIMIT] + "..."
    click.echo(f"      Description: {desc or '(none)'}")


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
    """Fill in missing metadata (and cover images) via Metron and Google Books,
    across both the comics and manga library files."""
    config = load_config(config_path)
    covers_dir = config.data_dir / "covers"

    sources = []
    if config.metron.is_configured:
        sources.append(MetronSource(config.metron.username, config.metron.password))
    else:
        click.echo("Metron not configured (skipping) — fill in config.yaml to enable.")
    sources.append(GoogleBooksSource(config.google_books.api_key))

    total_updated = 0
    total_records = 0
    for filename in ("library_comics.json", "library_manga.json"):
        library_path = config.data_dir / filename
        records = load_library(library_path)
        if not records:
            click.echo(f"No records found in {filename} — run `scan` first.")
            continue
        updated = enrich_all(records, sources, covers_dir, force=force)
        save_library(library_path, records)
        click.echo(f"{filename}: enriched {updated} of {len(records)} record(s).")
        total_updated += updated
        total_records += len(records)

    click.echo(f"Total: enriched {total_updated} of {total_records} record(s).")


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


@main.command("check-pulls")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
def check_pulls_cmd(config_path: str) -> None:
    """Fetches the configured League of Comic Geeks pull-list calendar,
    resolves every not-yet-processed already-released item via Metron, and
    adds each as a new physical record (or merges it into a matching
    digital one) — after showing a preview and asking for confirmation.
    Commits the result locally when anything changed — never pushes."""
    config = load_config(config_path)
    if not config.pull_list.calendar_url:
        click.echo("No pull_list.calendar_url configured in config.yaml.")
        return
    if not config.metron.is_configured:
        click.echo("Metron not configured — check-pulls requires it (fill in config.yaml).")
        return

    metron = MetronSource(config.metron.username, config.metron.password)
    library_path = config.data_dir / "library_comics.json"
    covers_dir = config.data_dir / "covers"
    state_path = config.data_dir / "pull_state.json"

    records = load_library(library_path)
    state = load_state(state_path)

    items = fetch_pulled_items(config.pull_list.calendar_url)
    today = date.today()
    pending = [
        item for item in items
        if item.event_uid not in state["processed_uids"] and item.release_date <= today
    ]

    added_results: list[ResolveResult] = []
    merged_results: list[ResolveResult] = []
    flag_lines: list[str] = []
    for item in pending:
        try:
            result = resolve_and_add(item, records, metron, covers_dir)
        except Exception as e:
            result = ResolveResult("flagged", item.title, reason=f"lookup failed: {e}")
        state["processed_uids"].append(item.event_uid)
        if result.outcome == "added":
            added_results.append(result)
        elif result.outcome == "merged":
            merged_results.append(result)
        else:
            flag_lines.append(f"{item.title}: {result.reason}")

    click.echo(f"Checked {len(items)} pull-list item(s), {len(pending)} new.")

    if added_results or merged_results:
        click.echo("")
        click.echo("The following comics will be added:")
        for result in (*added_results, *merged_results):
            record = result.record
            title = f"{record.series} #{record.issue_number}" if record.series and record.issue_number else record.title
            _echo_comic_preview(title=title, year=record.year, author=record.author, description=record.description)
        click.echo("")
        if not click.confirm(f"Add {len(added_results)} new and merge {len(merged_results)} into existing records?", default=False):
            click.echo("Cancelled — no changes made.")
            return

    added, merged, flagged = len(added_results), len(merged_results), len(flag_lines)
    added_titles = [r.title for r in added_results]
    merged_titles = [r.title for r in merged_results]

    save_library(library_path, records)
    save_state(state_path, state)

    click.echo(f"Added {added}, merged {merged} into existing records, flagged {flagged}.")
    for line in flag_lines:
        click.echo(f"  FLAGGED: {line}")

    if pending:
        message_lines = [f"check-pulls: added {added}, merged {merged}, flagged {flagged}", ""]
        if added_titles:
            message_lines.append("Added:")
            message_lines.extend(f"- {t}" for t in added_titles)
        if merged_titles:
            message_lines.append("Merged into existing records:")
            message_lines.extend(f"- {t}" for t in merged_titles)
        if flag_lines:
            message_lines.append("Flagged (needs manual review):")
            message_lines.extend(f"- {line}" for line in flag_lines)
        try:
            if commit_if_changed([str(library_path), str(state_path)], "\n".join(message_lines)):
                click.echo("Committed to git.")
        except Exception as e:
            click.echo(f"Warning: could not commit to git: {e}")


@main.command("add-comic")
@click.argument("url")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--physical", is_flag=True, help="Add as a physical copy instead of digital (default).")
def add_comic_cmd(url: str, config_path: str, physical: bool) -> None:
    """Adds a single comic from its League of Comic Geeks issue page —
    the manual counterpart to check-pulls, for a digital buy (default) or
    a one-off physical add outside the weekly pull-list flow. Shows a
    preview of the fetched info and asks for confirmation before writing
    anything; commits the result locally when confirmed — never pushes."""
    if not comic_geeks.is_comic_geeks_url(url):
        raise click.ClickException(f"Only leagueofcomicgeeks.com links are supported: {url!r}")

    info = comic_geeks.fetch_issue(url)
    if not info:
        raise click.ClickException("Couldn't read that Comic Geeks page — check the URL, or the site may be unreachable.")

    new_format = "print" if physical else "digital"

    title = f"{info['series']} #{info['issue_number']}" if info.get("series") and info.get("issue_number") else info.get("series") or url
    click.echo("")
    _echo_comic_preview(title=title, year=info.get("year"), author=info.get("author"), description=info.get("description"))
    click.echo("")
    if not click.confirm(f"Add this as {new_format}?", default=False):
        click.echo("Cancelled — no changes made.")
        return

    config = load_config(config_path)
    library_path = config.data_dir / "library_comics.json"
    covers_dir = config.data_dir / "covers"
    records = load_library(library_path)

    if info.get("upc"):
        record_id = f"upc-{info['upc']}"
    else:
        comic_id = comic_geeks.extract_comic_id(url)
        if comic_id is None:
            raise click.ClickException("Couldn't determine a Comic Geeks id from that URL.")
        record_id = f"cgeeks-{comic_id}"

    existing = records.get(record_id)
    if existing is None and info.get("series") and info.get("issue_number") and is_matchable(info["series"], info["issue_number"]):
        existing = find_matching_record(records, info["series"], info["issue_number"])

    if existing is not None:
        changed = False
        if new_format not in existing.formats:
            existing.formats.append(new_format)
            changed = True
        if info.get("upc") and not existing.upc:
            existing.upc = info["upc"]
            changed = True
        save_library(library_path, records)
        click.echo(f"Already in your library as {existing.id} — added '{new_format}' to its formats.")
        if changed:
            message = f"Merge {new_format} format into {existing.series or existing.title} ({existing.id})"
            try:
                if commit_if_changed([str(library_path)], message):
                    click.echo("Committed to git.")
            except Exception as e:
                click.echo(f"Warning: could not commit to git: {e}")
        return

    if info.get("series") and info.get("issue_number"):
        title = f"{info['series']} #{info['issue_number']}"
    else:
        title = info.get("series") or url
    record = ComicRecord(id=record_id, title=title, type="comic", formats=[new_format])
    for field in ("series", "issue_number", "publisher", "year", "description", "author", "upc"):
        if info.get(field):
            setattr(record, field, info[field])
            record.metadata_source[field] = "comic_geeks"
    if info.get("_image_url"):
        download_cover(record, info["_image_url"], "comic_geeks", covers_dir)

    records[record.id] = record
    save_library(library_path, records)
    click.echo(f"Added {record.series or record.title} #{record.issue_number or '?'} ({record.id}) as {new_format}.")


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
        ViewerRequestHandler, directory=".", comics_path=comics_path, manga_path=manga_path, covers_dir=covers_dir,
    )
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        click.echo(f"Serving at http://127.0.0.1:{port}/viewer.html — Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nStopped.")


@main.command("sync-sheet")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
def sync_sheet_cmd(config_path: str) -> None:
    """Pushes the current comics library to the configured Google Sheet
    (full overwrite of the configured worksheet). Also the command to run
    for the first-time OAuth consent flow. Unlike the automatic sync
    add-comic/check-pulls trigger, errors here are not swallowed — this
    command's whole purpose is the sync itself."""
    config = load_config(config_path)
    if not config.google_sheets.is_configured:
        raise click.ClickException(
            "google_sheets not configured — fill in config.yaml "
            "(see docs/superpowers/specs/2026-09-07-google-sheets-sync-design.md)."
        )
    library_path = config.data_dir / "library_comics.json"
    records = load_library(library_path)
    sync_comics_to_sheet(records, config)
    click.echo(f"Synced {len(records)} comic(s) to the '{config.google_sheets.worksheet_name}' worksheet.")


if __name__ == "__main__":
    main()
