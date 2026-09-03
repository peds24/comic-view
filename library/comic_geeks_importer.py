"""Import Comic Geeks Excel exports (comics or manga — same sheet layout)
directly into an enriched library.

Unlike excel_importer.import_physical (local-pass-only, enrichment deferred
to a separate `enrich` run), this routes each row to a metadata source by
its own barcode's shape and fetches description/author/cover in the same
pass — which source to use depends on the code, not the record type.

Routing (matches the sources/order proven in the longbox app,
github.com/peds24/longbox, which also resolves scanned comic barcodes):
  - 17-digit Diamond UPC -> Metron exact issue lookup (`/issue/?upc=`),
    falling back to an exact series+issue-number lookup if Metron's UPC
    index doesn't have that specific code (a real, common gap)
  - 13-digit ISBN (978/979 prefix) -> Open Library first (title, author,
    publisher, year, cover — all in one call), Google Books as fallback for
    whatever Open Library doesn't have (mainly description, which Open
    Library has no field for at all)
  - no code, or a code Excel corrupted via float rounding -> exact
    series+issue-number Metron lookup when an issue number is known,
    otherwise fuzzy title+year search as a last resort
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from library.excel_importer import compute_physical_id, extract_issue, load_rows, normalize_series
from library.metadata_sources.google_books import GoogleBooksSource
from library.metadata_sources.metron import MetronSource
from library.metadata_sources.open_library import OpenLibrarySource
from library.models import ComicRecord

_DEFAULT_COVER_EXT = ".jpg"
_TRAILING_VOL_RE = re.compile(r",?\s*Vol(?:ume)?\.?\s*(\d+)\s*$", re.IGNORECASE)
_TRAILING_NUMBER_RE = re.compile(r"\s+(\d{1,3})\s*$")


def classify_code(value: object) -> tuple[str, str | None]:
    """(kind, normalized_code).

    kind is one of:
      "isbn"      - a 13-digit ISBN-13 (978/979 prefix), either bare or as
                    the first 13 digits of an 18-digit ISBN+5-digit price
                    add-on barcode (a common print-book EAN convention)
      "upc"       - clean numeric code of some other length (Diamond UPC etc.)
      "corrupted" - Excel silently rounded a long number to a float; the
                    original digits aren't recoverable from this cell
      "none"      - no code at all
    """
    if value is None or value == "":
        return "none", None
    if isinstance(value, float):
        return "corrupted", None
    code = str(value).strip()
    if not code.isdigit():
        return "none", None
    if len(code) == 13 and code.startswith(("978", "979")):
        return "isbn", code
    if len(code) == 18 and code.startswith(("978", "979")):
        return "isbn", code[:13]
    return "upc", code


def extract_manga_issue(full_title: str) -> str | None:
    """Manga volumes don't use '#N' like excel_importer.extract_issue expects
    — they're 'Series, Vol. N' or end with a bare trailing number."""
    match = _TRAILING_VOL_RE.search(full_title or "")
    if not match:
        match = _TRAILING_NUMBER_RE.search(full_title or "")
    return match.group(1) if match else None


def _download_cover(record: ComicRecord, url: str, source_name: str, covers_dir: Path) -> bool:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return False

    ext = Path(urlparse(url).path).suffix or _DEFAULT_COVER_EXT
    dest_dir = covers_dir / record.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / f"cover{ext}").write_bytes(resp.content)
    record.cover_path = f"{record.id}/cover{ext}"
    record.metadata_source["cover_path"] = source_name
    return True


def _fill_missing(record: ComicRecord, fields: dict, source_name: str) -> None:
    for field, value in fields.items():
        if value and not getattr(record, field, None):
            setattr(record, field, value)
            record.metadata_source[field] = source_name


def _enrich_by_upc(record: ComicRecord, upc: str, metron: MetronSource | None, covers_dir: Path) -> None:
    if metron is None:
        return
    try:
        issue = metron.find_issue_by_upc(upc)
    except Exception:
        issue = None
    if not issue:
        # Metron's exact-UPC index has real gaps (confirmed against the live
        # API — plenty of legitimate UPCs return zero results) — title
        # search is strictly better than leaving the record unenriched.
        _enrich_by_title(record, metron, covers_dir)
        return

    _fill_missing(
        record,
        {"description": issue.get("desc"), "author": MetronSource._extract_writer(issue)},
        "metron",
    )
    if issue.get("image"):
        _download_cover(record, issue["image"], "metron", covers_dir)


def _enrich_by_isbn(
    record: ComicRecord,
    isbn: str,
    google_books: GoogleBooksSource,
    open_library: OpenLibrarySource,
    covers_dir: Path,
) -> None:
    """Open Library first, Google Books as fallback for whatever Open
    Library doesn't have — the routing proven in the longbox app
    (github.com/peds24/longbox), which also uses these two sources for
    ISBN-coded books. Open Library's bibkeys endpoint covers title, author,
    publisher, year, and cover in one call; it has no description field,
    which is the main thing Google Books ends up contributing here."""
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
        _download_cover(record, cover_url, cover_source, covers_dir)


def _enrich_by_title(record: ComicRecord, metron: MetronSource | None, covers_dir: Path) -> None:
    """Fallback enrichment when there's no usable barcode. Prefers an exact
    series+issue-number lookup — for an ongoing series, title+year alone
    can't tell issue #14 from issue #22 (a year can span a dozen issues),
    which was previously causing multiple different issues to silently get
    the same wrong cover/description. Only falls back further to fuzzy
    title+year search when there's no issue number to match on (e.g. a
    TPB/collection) — never as a second attempt after an exact match fails,
    since that's what reintroduces the wrong-issue risk."""
    if metron is None:
        return
    query = record.series or record.title

    if record.issue_number:
        try:
            issue = metron.find_issue_by_series_and_number(query, record.issue_number, record.year)
        except Exception:
            issue = None
        if issue:
            _fill_missing(
                record,
                {"description": issue.get("desc"), "author": MetronSource._extract_writer(issue)},
                "metron",
            )
            if issue.get("image"):
                _download_cover(record, issue["image"], "metron", covers_dir)
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
        _download_cover(record, cover_url, "metron", covers_dir)


def import_comic_geeks_xlsx(
    path: str,
    record_type: str,
    records: dict[str, ComicRecord],
    *,
    metron: MetronSource | None,
    google_books: GoogleBooksSource,
    open_library: OpenLibrarySource,
    covers_dir: Path,
) -> dict[str, int]:
    """Reads a Comic Geeks 'Comics' sheet (used for both comics and manga
    exports — same column layout), enriches each new row via the source
    routed by its code, and adds it to `records` (mutated in place).
    """
    stats = {"new": 0, "skipped_not_in_collection": 0, "skipped_corrupted_code": 0, "skipped_duplicate": 0}
    rows = load_rows(path)

    for row in rows:
        if row.get("In Collection") != 1:
            stats["skipped_not_in_collection"] += 1
            continue

        full_title = row.get("Full Title") or ""
        series = normalize_series(row.get("Series Name") or "") or None
        issue_number = extract_issue(full_title)
        if issue_number is None and record_type == "manga":
            issue_number = extract_manga_issue(full_title)

        year = None
        release_date = row.get("Release Date")
        if release_date and str(release_date)[:4].isdigit():
            year = int(str(release_date)[:4])

        code_value = row["UPC / ISBN"] if "UPC / ISBN" in row else row.get("ISBN")
        kind, code = classify_code(code_value)

        if kind == "corrupted":
            stats["skipped_corrupted_code"] += 1
            continue

        record_id = f"{kind}-{code}" if code else compute_physical_id(series or "", full_title)
        if record_id in records:
            stats["skipped_duplicate"] += 1
            continue

        record = ComicRecord(
            id=record_id,
            title=full_title,
            type=record_type,
            series=series,
            issue_number=issue_number,
            publisher=row.get("Publisher Name") or None,
            year=year,
            isbn=code,
            status="read" if row.get("Marked Read") == 1 else "unread",
            formats=["print"],
        )

        if kind == "isbn":
            _enrich_by_isbn(record, code, google_books, open_library, covers_dir)
        elif kind == "upc":
            _enrich_by_upc(record, code, metron, covers_dir)
        else:
            _enrich_by_title(record, metron, covers_dir)

        records[record_id] = record
        stats["new"] += 1

    return stats
