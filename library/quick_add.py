"""Add a single new comic or manga to the collection from an identifier the
owner already has in hand — a UPC/ISBN/League of Comic Geeks link for a
comic, or a title/ISBN for manga — rather than a batch workbook
(`physical_importer.py`) or a local scanned file (`scanner.py`). Powers the
`/api/add-comic` and `/api/add-manga` routes `comic-library serve` exposes
to the web app's owner-only quick-add form.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from library.manual_attach import LinkAttachError, attach_comic_geeks_issue
from library.matching import find_digital_match, is_matchable
from library.metadata_sources import comic_geeks
from library.models import ComicRecord


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
    if record.series and record.issue_number and is_matchable(record.title, record.issue_number):
        match = find_digital_match(records, record.series, record.issue_number)

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
    record = ComicRecord(id="pending", title="", type="comic", formats=list(formats))
    try:
        attach_comic_geeks_issue(record, url, covers_dir)
    except LinkAttachError as e:
        raise QuickAddError(str(e)) from e

    if record.series and record.issue_number:
        record.title = f"{record.series} #{record.issue_number}"
    else:
        record.title = record.series or ""
    record.id = f"cg-{_comic_geeks_id_from_url(url)}"

    return _merge_or_add(records, record, "upc", record.upc)


def add_comic(
    records: dict[str, ComicRecord], raw_input: str, formats: list[str], *,
    metron, google_books, open_library, covers_dir: Path,
) -> AddResult:
    raw_input = raw_input.strip()

    if comic_geeks.is_comic_geeks_url(raw_input):
        return _add_comic_from_comic_geeks_link(records, raw_input, formats, covers_dir)

    raise QuickAddError("Comics need a UPC, ISBN, or a League of Comic Geeks link.")
