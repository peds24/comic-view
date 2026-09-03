"""Import physical comics/manga from one workbook with two sheets: "Comics"
and "Manga" (columns: Name, UPC/ISBN; sheet names matched case-
insensitively).

The Manga sheet's codes are always ISBNs. The Comics sheet is mixed: an
individual issue carries a Diamond UPC, but a collected edition (TPB/HC/
omnibus) is stocked in bookstores under a real ISBN instead — those codes
start with "9" (ISBN-13's 978/979 prefix), and are routed to Open Library
+ Google Books just like a manga row, not to Metron, which has no ISBN
index. A comics-sheet row is still typed "comic"; only the enrichment
source and the `isbn` vs `upc` field it fills depend on the code's shape.

Each row is enriched in the same pass it's read (no separate `enrich` run
needed), then merged into an existing digital record if the metadata
fetched back (series + issue/volume number) matches one — otherwise it
becomes a new print-only record. A barcode already seen on a previous run
(whether it ended up merged into a digital record or as its own print-only
record) is skipped without hitting the network again.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import openpyxl

from library.covers import download_cover
from library.matching import (
    extract_issue,
    extract_manga_issue,
    find_digital_match,
    is_matchable,
    strip_manga_volume_suffix,
)
from library.metadata_sources.google_books import GoogleBooksSource
from library.metadata_sources.metron import MetronSource, year_from_issue
from library.metadata_sources.open_library import OpenLibrarySource
from library.models import ComicRecord

_COMICS_SHEET = "comics"
_MANGA_SHEET = "manga"


def _find_sheet(wb: openpyxl.Workbook, name: str):
    for sheet_name in wb.sheetnames:
        if sheet_name.strip().lower() == name:
            return wb[sheet_name]
    return None


def _load_rows(ws) -> list[dict]:
    headers = [c.value for c in ws[1]]
    return [dict(zip(headers, row)) for row in ws.iter_rows(min_row=2, values_only=True)]


def count_rows(path: str) -> int:
    """Total data rows across both sheets — lets a caller size a progress
    bar before calling import_physical_xlsx (which reopens the workbook)."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    total = 0
    for name in (_COMICS_SHEET, _MANGA_SHEET):
        ws = _find_sheet(wb, name)
        if ws is not None:
            total += max(ws.max_row - 1, 0)
    return total


def _normalize_code(value: object) -> tuple[str | None, bool]:
    """Returns (normalized_digit_string_or_None, corrupted).

    Excel can silently round a long barcode to a float (losing digits) —
    that shows up here as a float value, which is unrecoverable from this
    cell alone, so it's reported as corrupted rather than looked up wrong.
    """
    if value is None or value == "":
        return None, False
    if isinstance(value, float):
        return None, True
    code = str(value).strip()
    if not code.isdigit():
        return None, False
    return code, False


def _fill_missing(record: ComicRecord, fields: dict, source_name: str) -> None:
    for field, value in fields.items():
        if value and not getattr(record, field, None):
            setattr(record, field, value)
            record.metadata_source[field] = source_name


def _apply_metron_issue(record: ComicRecord, issue: dict, covers_dir: Path) -> None:
    series = issue.get("series")
    series_name = series.get("name") if isinstance(series, dict) else None
    publisher = issue.get("publisher")
    publisher_name = publisher.get("name") if isinstance(publisher, dict) else None
    _fill_missing(
        record,
        {
            "series": series_name,
            "issue_number": issue.get("number"),
            "publisher": publisher_name,
            "year": year_from_issue(issue),
            "description": issue.get("desc"),
            "author": MetronSource._extract_writer(issue),
        },
        "metron",
    )
    if issue.get("image"):
        download_cover(record, issue["image"], "metron", covers_dir)


def _enrich_comic_by_title(record: ComicRecord, metron: MetronSource, covers_dir: Path) -> None:
    """Fallback enrichment when Metron's UPC index has no entry for this
    code (a real, common gap). Prefers an exact series+issue-number lookup
    over fuzzy title+year search, for the same reason as the UPC path —
    year alone can't tell issue #14 from issue #22 in an ongoing series."""
    query = record.series or record.title
    if record.issue_number:
        try:
            issue = metron.find_issue_by_series_and_number(query, record.issue_number, record.year)
        except Exception:
            issue = None
        if issue:
            _apply_metron_issue(record, issue, covers_dir)
        return

    try:
        partial = metron.search(query, record.year)
    except Exception:
        partial = {}
    _fill_missing(record, partial, "metron")

    try:
        cover_url = metron.cover_image_url(query, record.year)
    except Exception:
        cover_url = None
    if cover_url:
        download_cover(record, cover_url, "metron", covers_dir)


def _enrich_comic(record: ComicRecord, upc: str, metron: MetronSource | None, covers_dir: Path) -> None:
    if metron is None:
        return
    try:
        issue = metron.find_issue_by_upc(upc)
    except Exception:
        issue = None
    if not issue:
        _enrich_comic_by_title(record, metron, covers_dir)
        return
    _apply_metron_issue(record, issue, covers_dir)


def _enrich_isbn(
    record: ComicRecord,
    isbn: str,
    google_books: GoogleBooksSource,
    open_library: OpenLibrarySource,
    covers_dir: Path,
) -> None:
    """Open Library first, Google Books as fallback for whatever Open
    Library doesn't have — Open Library's bibkeys endpoint covers title,
    author, publisher, year, and cover in one call, but has no description
    field, which is the main thing Google Books ends up contributing.
    Used for both manga-sheet rows and ISBN-shaped comics-sheet rows."""
    try:
        ol_info = open_library.lookup_isbn(isbn)
    except Exception:
        ol_info = {}
    _fill_missing(
        record,
        {k: ol_info.get(k) for k in ("author", "publisher", "year", "description")},
        "open_library",
    )
    cover_url = ol_info.get("_image_url")
    cover_source = "open_library"

    if not record.description or not cover_url:
        try:
            gb_info = google_books.lookup_isbn(isbn)
        except Exception:
            gb_info = {}
        _fill_missing(
            record,
            {k: gb_info.get(k) for k in ("author", "publisher", "year", "description")},
            "google_books",
        )
        if not cover_url and gb_info.get("_image_url"):
            cover_url = gb_info["_image_url"]
            cover_source = "google_books"

    if cover_url:
        download_cover(record, cover_url, cover_source, covers_dir)


def _is_isbn_shaped(code: str) -> bool:
    """ISBN-13 always starts with the 978/979 prefix — a Diamond UPC for a
    single comic issue never does. Both prefixes start with "9", which is
    enough to distinguish the two in this dataset (Diamond UPCs seen here
    start with 7 or 75/76)."""
    return code.startswith("9")


def _truncate_isbn(code: str) -> str:
    """A print book's barcode is sometimes an 18-digit EAN — ISBN-13 plus a
    5-digit price add-on, a common convention — rather than a bare 13-digit
    ISBN-13. Only the first 13 digits are the actual ISBN; the rest doesn't
    correspond to any real edition and would fail every lookup."""
    return code[:13] if len(code) > 13 else code


def _import_comic_row(
    row: dict,
    records: dict[str, ComicRecord],
    metron: MetronSource | None,
    google_books: GoogleBooksSource,
    open_library: OpenLibrarySource,
    covers_dir: Path,
    stats: dict[str, int],
    seen_upcs: set[str],
    seen_isbns: set[str],
) -> None:
    title = (row.get("Name") or "").strip()
    raw_code = row.get("UPC/ISBN")
    if not title and not raw_code:
        return  # blank trailing row

    code, corrupted = _normalize_code(raw_code)
    if corrupted:
        stats["skipped_corrupted_code"] += 1
        return
    if not code:
        stats["skipped_blank_code"] += 1
        return

    is_isbn = _is_isbn_shaped(code)
    if is_isbn:
        code = _truncate_isbn(code)
    seen = seen_isbns if is_isbn else seen_upcs
    if code in seen:
        stats["skipped_duplicate"] += 1
        return

    record = ComicRecord(
        id=f"{'isbn' if is_isbn else 'upc'}-{code}", title=title, type="comic",
        issue_number=extract_issue(title), formats=["print"],
        **({"isbn": code} if is_isbn else {"upc": code}),
    )
    if is_isbn:
        _enrich_isbn(record, code, google_books, open_library, covers_dir)
    else:
        _enrich_comic(record, code, metron, covers_dir)

    match = None
    if record.series and record.issue_number and is_matchable(record.title, record.issue_number):
        match = find_digital_match(records, record.series, record.issue_number)

    if match is not None:
        if "print" not in match.formats:
            match.formats.append("print")
        if is_isbn and not match.isbn:
            match.isbn = code
        elif not is_isbn and not match.upc:
            match.upc = code
        stats["comics_merged"] += 1
    else:
        records[record.id] = record
        stats["comics_added"] += 1

    seen.add(code)


def _import_manga_row(
    row: dict,
    records: dict[str, ComicRecord],
    google_books: GoogleBooksSource,
    open_library: OpenLibrarySource,
    covers_dir: Path,
    stats: dict[str, int],
    seen_isbns: set[str],
) -> None:
    title = (row.get("Name") or "").strip()
    raw_code = row.get("UPC/ISBN")
    if not title and not raw_code:
        return  # blank trailing row

    code, corrupted = _normalize_code(raw_code)
    if corrupted:
        stats["skipped_corrupted_code"] += 1
        return
    if not code:
        stats["skipped_blank_code"] += 1
        return
    code = _truncate_isbn(code)
    if code in seen_isbns:
        stats["skipped_duplicate"] += 1
        return

    issue_number = extract_manga_issue(title)
    record = ComicRecord(
        id=f"isbn-{code}", title=title, type="manga",
        series=strip_manga_volume_suffix(title) if issue_number else None,
        issue_number=issue_number, isbn=code, formats=["print"],
    )
    _enrich_isbn(record, code, google_books, open_library, covers_dir)

    match = None
    if record.series and record.issue_number:
        match = find_digital_match(records, record.series, record.issue_number)

    if match is not None:
        if "print" not in match.formats:
            match.formats.append("print")
        if not match.isbn:
            match.isbn = code
        stats["manga_merged"] += 1
    else:
        records[record.id] = record
        stats["manga_added"] += 1

    seen_isbns.add(code)


def import_physical_xlsx(
    path: str,
    records: dict[str, ComicRecord],
    *,
    metron: MetronSource | None,
    google_books: GoogleBooksSource,
    open_library: OpenLibrarySource,
    covers_dir: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    """Reads the 'comics' and 'manga' sheets from `path` and adds/merges
    each new row into `records` (mutated in place).

    If given, on_progress(completed, total) is called after each row is
    processed (across both sheets, whether added, merged, or skipped) —
    lets a caller show a progress bar over an import that can take a while,
    since every row does at least one network lookup.
    """
    stats = {
        "comics_added": 0, "comics_merged": 0,
        "manga_added": 0, "manga_merged": 0,
        "skipped_corrupted_code": 0, "skipped_blank_code": 0, "skipped_duplicate": 0,
    }
    seen_upcs = {r.upc for r in records.values() if r.upc}
    seen_isbns = {r.isbn for r in records.values() if r.isbn}

    wb = openpyxl.load_workbook(path, data_only=True)

    comics_ws = _find_sheet(wb, _COMICS_SHEET)
    comics_rows = _load_rows(comics_ws) if comics_ws is not None else []
    manga_ws = _find_sheet(wb, _MANGA_SHEET)
    manga_rows = _load_rows(manga_ws) if manga_ws is not None else []

    total = len(comics_rows) + len(manga_rows)
    completed = 0

    for row in comics_rows:
        _import_comic_row(row, records, metron, google_books, open_library, covers_dir, stats, seen_upcs, seen_isbns)
        completed += 1
        if on_progress:
            on_progress(completed, total)

    for row in manga_rows:
        _import_manga_row(row, records, google_books, open_library, covers_dir, stats, seen_isbns)
        completed += 1
        if on_progress:
            on_progress(completed, total)

    return stats
