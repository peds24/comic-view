"""Add a single new comic or manga to the collection from an identifier the
owner already has in hand — a UPC/ISBN/League of Comic Geeks link for a
comic, or a title/ISBN for manga — rather than a batch workbook
(`physical_importer.py`) or a local scanned file (`scanner.py`). Powers the
`/api/add-comic` and `/api/add-manga` routes `comic-library serve` exposes
to the web app's owner-only quick-add form.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from library.manual_attach import LinkAttachError, attach_comic_geeks_issue
from library.matching import extract_manga_issue, find_digital_match, is_matchable, strip_manga_volume_suffix
from library.metadata_sources import comic_geeks
from library.models import ComicRecord
from library.physical_importer import enrich_comic_by_upc, enrich_isbn, is_isbn_shaped, truncate_isbn


class QuickAddError(Exception):
    """Raised when a record genuinely can't be built from the given input:
    an unrecognized input shape, or an unreadable Comic Geeks link. A
    lookup that simply finds nothing does NOT raise — a bare record is
    still created from what the user typed, same tolerance as the batch
    importer's title-search fallback."""


@dataclass
class AddResult:
    record: ComicRecord
    merged: bool


def _merge_or_add(records: dict[str, ComicRecord], record: ComicRecord, code_field: str | None, code: str | None) -> AddResult:
    match = None
    # Deliberately stricter than physical_importer._import_manga_row's merge
    # gate (which only checks `series and issue_number`, no is_matchable):
    # quick-add is a single, owner-driven add, so it's worth the extra
    # caution to avoid merging a manga title that matches a non-matchable
    # keyword like "Deluxe Edition" into an unrelated digital record. Keep
    # this stricter than the batch importer rather than "fixing" it to match.
    if record.series and record.issue_number and is_matchable(record.title, record.issue_number):
        match = find_digital_match(records, record.series, record.issue_number)
    if match is None:
        # Re-adding the same UPC/ISBN/Comic Geeks link/manga a second time
        # must not silently clobber whatever's already stored under this
        # exact id (a hand-edited title, year, status, cover...) — the
        # batch importer guards the equivalent case with its
        # seen_upcs/seen_isbns sets; here there's no "skip" outcome to
        # return, so it's treated as a merge into the existing record.
        match = records.get(record.id)

    if match is not None:
        for fmt in record.formats:
            if fmt not in match.formats:
                match.formats.append(fmt)
        if code_field and code and not getattr(match, code_field, None):
            setattr(match, code_field, code)
        return AddResult(record=match, merged=True)

    records[record.id] = record
    return AddResult(record=record, merged=False)


_COMIC_GEEKS_ID_RE = re.compile(r"/comic/(\d+)")


def _comic_geeks_id_from_url(url: str) -> str:
    """Pulls the numeric issue id out of a full issue URL
    (`.../comic/6297209/absolute-batman-16` -> `"6297209"`), or returns the
    url unchanged if it's already a bare id — mirrors what
    `comic_geeks.fetch_issue` itself accepts, without reaching into that
    module's private `_resolve_url` helper."""
    match = _COMIC_GEEKS_ID_RE.search(url)
    return match.group(1) if match else url.strip()


def _add_comic_from_comic_geeks_link(records: dict[str, ComicRecord], url: str, formats: list[str], covers_dir: Path) -> AddResult:
    # The id is computed up front (not assigned after attach_comic_geeks_issue
    # returns) because that call downloads the cover using record.id at the
    # time it runs — if the record were still "pending" then, every Comic
    # Geeks add would download to the same data/covers/pending/cover.jpg,
    # clobbering the previous add's cover.
    record = ComicRecord(id=f"cg-{_comic_geeks_id_from_url(url)}", title="", type="comic", formats=list(formats))
    try:
        attach_comic_geeks_issue(record, url, covers_dir)
    except LinkAttachError as e:
        raise QuickAddError(str(e)) from e

    if record.series and record.issue_number:
        record.title = f"{record.series} #{record.issue_number}"
    else:
        # Never leave the title empty — an empty-titled record renders as a
        # blank, unrecoverable card (_update_title refuses an empty title),
        # so fall back to the parsed id as a placeholder, same convention as
        # the UPC/ISBN path in _add_comic_from_code.
        record.title = record.series or record.id

    return _merge_or_add(records, record, "upc", record.upc)


def _add_comic_from_code(records: dict[str, ComicRecord], code: str, formats: list[str], *, metron, google_books, open_library, covers_dir: Path) -> AddResult:
    is_isbn = is_isbn_shaped(code)
    if is_isbn:
        code = truncate_isbn(code)

    record = ComicRecord(
        id=f"{'isbn' if is_isbn else 'upc'}-{code}", title=code, type="comic", formats=list(formats),
        **({"isbn": code} if is_isbn else {"upc": code}),
    )
    if is_isbn:
        enrich_isbn(record, code, google_books, open_library, covers_dir)
    else:
        enrich_comic_by_upc(record, code, metron, covers_dir)

    if record.series and record.issue_number:
        record.title = f"{record.series} #{record.issue_number}"

    code_field = "isbn" if is_isbn else "upc"
    return _merge_or_add(records, record, code_field, code)


def add_comic(
    records: dict[str, ComicRecord], raw_input: str, formats: list[str], *,
    metron, google_books, open_library, covers_dir: Path,
) -> AddResult:
    raw_input = raw_input.strip()

    if comic_geeks.is_comic_geeks_url(raw_input):
        return _add_comic_from_comic_geeks_link(records, raw_input, formats, covers_dir)

    if raw_input.isdigit():
        return _add_comic_from_code(
            records, raw_input, formats,
            metron=metron, google_books=google_books, open_library=open_library, covers_dir=covers_dir,
        )

    raise QuickAddError("Comics need a UPC, ISBN, or a League of Comic Geeks link.")


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled"


def add_manga(
    records: dict[str, ComicRecord], raw_input: str, formats: list[str], *,
    google_books, open_library, covers_dir: Path,
) -> AddResult:
    raw_input = raw_input.strip()

    if raw_input.isdigit():
        code = truncate_isbn(raw_input)
        record = ComicRecord(id=f"isbn-{code}", title=code, type="manga", isbn=code, formats=list(formats))
        enrich_isbn(record, code, google_books, open_library, covers_dir)
        code_field, code_value = "isbn", code
    else:
        title = raw_input
        issue_number = extract_manga_issue(title)
        record = ComicRecord(
            id=f"manual-{_slugify(title)}-{hashlib.sha1(title.encode()).hexdigest()[:8]}",
            title=title, type="manga",
            series=strip_manga_volume_suffix(title) if issue_number else None,
            issue_number=issue_number, formats=list(formats),
        )
        try:
            partial = google_books.search(title)
        except Exception:
            partial = {}
        for field, value in partial.items():
            if value and not getattr(record, field, None):
                setattr(record, field, value)
                record.metadata_source[field] = "google_books"
        try:
            cover_url = google_books.cover_image_url(title)
        except Exception:
            cover_url = None
        if cover_url:
            from library.covers import download_cover
            download_cover(record, cover_url, "google_books", covers_dir)
        code_field, code_value = None, None

    return _merge_or_add(records, record, code_field, code_value)
