"""Import physical manga from a barcode-scanner CSV export (ISBN only —
no title, series, or any other identifying info in the source file).

Unlike excel_importer.py, this import is inherently network-bound: a bare
ISBN can only be identified by looking it up. Each row does a Google Books
ISBN-exact lookup for metadata, then (since roughly half of exact editions
have no cover on Google Books, confirmed against the real export) falls back
to a title search for a cover image. preview_pages stays empty — same
reasoning as excel_importer.py, no legitimate source for interior pages.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from library.excel_importer import find_digital_match
from library.metadata_sources.google_books import GoogleBooksSource
from library.models import ComicRecord

_VOL_RE = re.compile(r",?\s*Vol(?:ume)?\.?\s*(\d+)\s*$", re.IGNORECASE)
_TRAILING_NUMBER_RE = re.compile(r"\s+(\d{1,3})\s*$")
_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")

# Titles containing any of these are collected/variant editions — never
# attempted against a single-volume digital match, always physical-only.
_NON_MATCHABLE_KEYWORDS = (
    "omnibus", "compendium", "edition", "collection", "vizbig",
    "3-in-1", "box set", "boxset",
)

_DEFAULT_COVER_EXT = ".jpg"


def is_valid_isbn13(code: str) -> bool:
    return code.isdigit() and len(code) == 13 and code.startswith(("978", "979"))


def load_csv_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_title(title: str) -> tuple[str, str | None]:
    """Splits a Google Books title into (series, volume). volume is None for
    one-shots/collections with no detectable volume number."""
    match = _VOL_RE.search(title)
    if not match:
        match = _TRAILING_NUMBER_RE.search(title)
    if not match:
        return title.strip(), None

    series = title[: match.start()].rstrip(" ,:-")
    series = _TRAILING_PAREN_RE.sub("", series).strip()
    return series, match.group(1)


def is_matchable(title: str, volume: str | None) -> bool:
    if volume is None:
        return False
    lowered = title.lower()
    return not any(keyword in lowered for keyword in _NON_MATCHABLE_KEYWORDS)


def _fetch_cover(record: ComicRecord, title: str, image_url: str | None, source: GoogleBooksSource, covers_dir: Path) -> None:
    if not image_url:
        try:
            image_url = source.cover_image_url(title)
        except Exception:
            image_url = None
    if not image_url:
        return

    try:
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
    except Exception:
        return

    ext = Path(urlparse(image_url).path).suffix or _DEFAULT_COVER_EXT
    dest_dir = covers_dir / record.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / f"cover{ext}").write_bytes(resp.content)
    record.cover_path = f"{record.id}/cover{ext}"
    record.metadata_source["cover_path"] = source.name


def import_isbn_csv(
    records: dict[str, ComicRecord], rows: list[dict], source: GoogleBooksSource, covers_dir: Path
) -> tuple[int, int, int, int]:
    """Merges/adds physical manga entries into records (mutated in place).

    Returns (merged_count, new_count, skipped_invalid_code, skipped_no_result).
    """
    merged = 0
    new = 0
    skipped_invalid = 0
    skipped_no_result = 0

    for row in rows:
        isbn = (row.get("text") or "").strip()
        if not is_valid_isbn13(isbn):
            skipped_invalid += 1
            continue

        comic_id = f"isbn-{isbn}"
        if comic_id in records:
            continue  # already imported

        try:
            info = source.lookup_isbn(isbn)
        except Exception:
            info = {}
        if not info or not info.get("title"):
            skipped_no_result += 1
            continue

        title = info["title"]
        series, volume = parse_title(title)
        matchable = is_matchable(title, volume)

        match = None
        if matchable and series and volume:
            match = find_digital_match(records, series, volume)

        if match is not None:
            if "physical" not in match.formats:
                match.formats.append("physical")
                merged += 1
            continue

        record = ComicRecord(
            id=comic_id,
            title=title,
            type="manga",
            series=series or None,
            issue_number=volume,
            author=info.get("author"),
            year=info.get("year"),
            publisher=info.get("publisher"),
            description=info.get("description"),
            status="unread",
            formats=["physical"],
            metadata_source={k: "google_books" for k in ("author", "year", "publisher", "description") if info.get(k)},
        )
        _fetch_cover(record, title, info.get("_image_url"), source, covers_dir)
        records[comic_id] = record
        new += 1

    return merged, new, skipped_invalid, skipped_no_result
