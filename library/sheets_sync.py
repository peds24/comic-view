"""Mirrors data/library_comics.json to a live Google Sheet.

Full-overwrite sync only: every sync_comics_to_sheet call clears the
target worksheet and rewrites it from the current library contents.
Deliberately not incremental — see
docs/superpowers/specs/2026-09-07-google-sheets-sync-design.md.
"""
from __future__ import annotations

from library.models import ComicRecord

_HEADER = ["Title", "Series", "Issue #", "Author", "Year", "Publisher", "Status", "Formats", "Added Date"]


def _comic_to_row(record: ComicRecord) -> list[str]:
    if record.series and record.issue_number:
        title = f"{record.series} #{record.issue_number}"
    else:
        title = record.title
    return [
        title,
        record.series or "",
        record.issue_number or "",
        record.author or "",
        str(record.year) if record.year else "",
        record.publisher or "",
        record.status,
        ", ".join(record.formats),
        record.added_date,
    ]
