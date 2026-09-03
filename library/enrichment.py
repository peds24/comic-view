"""Fill in missing ComicRecord fields using online metadata sources.

Metron is tried first (comics-focused), Google Books second (broader
coverage, better for manga). Idempotent: a record with no missing fields and
an existing cover is skipped unless force=True.

Also fetches a cover image for records with no cover_path (print-only
comics imported via physical_importer have no local archive to extract a
cover from). preview_pages is intentionally left empty for these —
legitimate metadata APIs expose a cover image, not interior page scans.

Cover source routing (see refetch_physical_covers): Metron is preferred for
single comic issues (best coverage/accuracy for individual back issues),
Google Books for manga and collected editions/TPBs (better catalog coverage
for those formats than Metron, which is single-issue-focused). Both are
still tried as a fallback if the preferred one has nothing, to maximize
actual cover coverage.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests

from library.matching import is_matchable
from library.metadata_sources.base import MetadataSource
from library.models import ComicRecord

_DEFAULT_COVER_EXT = ".jpg"


def enrich_record(
    record: ComicRecord, sources: list[MetadataSource], covers_dir: Path, force: bool = False
) -> bool:
    """Mutates record in place. Returns True if anything changed."""
    needs_work = force or record.missing_fields() or not record.cover_path
    if not needs_work:
        return False

    changed = False
    for source in sources:
        if not force and not record.missing_fields():
            break
        query_title = record.series or record.title
        try:
            partial = source.search(query_title, record.year)
        except Exception:
            continue
        if not partial:
            continue
        before = record.to_dict()
        record.apply_partial(partial, source.name)
        if record.to_dict() != before:
            changed = True

    if force or not record.cover_path:
        if _fetch_cover(record, _ordered_cover_sources(record, sources), covers_dir):
            changed = True

    return changed


def enrich_all(
    records: dict[str, ComicRecord], sources: list[MetadataSource], covers_dir: Path, force: bool = False
) -> int:
    updated = 0
    for record in records.values():
        if enrich_record(record, sources, covers_dir, force=force):
            updated += 1
    return updated


def _is_single_issue_comic(record: ComicRecord) -> bool:
    """True for an individual comic issue (not a TPB/HC/omnibus/annual/etc,
    which matching.is_matchable() already treats as "not a single issue"
    via the same title-keyword check used for digital/physical matching)."""
    return record.type == "comic" and is_matchable(record.title, record.issue_number)


def _ordered_cover_sources(record: ComicRecord, sources: list[MetadataSource]) -> list[MetadataSource]:
    """Reorders sources so the preferred one for this record's kind is tried
    first, with the rest kept as fallback."""
    if record.type == "manga" or not _is_single_issue_comic(record):
        preferred_name = "google_books"
    else:
        preferred_name = "metron"

    preferred = [s for s in sources if s.name == preferred_name]
    rest = [s for s in sources if s.name != preferred_name]
    return preferred + rest


def refetch_physical_covers(
    records: dict[str, ComicRecord], sources: list[MetadataSource], covers_dir: Path
) -> int:
    """Re-fetches covers for every print-only record (formats == ["print"]),
    using the source routing in _ordered_cover_sources, overwriting whatever
    cover it currently has. Never touches digital or digital+print records —
    those have a real cover extracted from the scanned archive."""
    updated = 0
    for record in records.values():
        if record.formats != ["print"]:
            continue
        if _fetch_cover(record, _ordered_cover_sources(record, sources), covers_dir):
            updated += 1
    return updated


def _fetch_cover(record: ComicRecord, sources: list[MetadataSource], covers_dir: Path) -> bool:
    query_title = record.series or record.title
    for source in sources:
        try:
            url = source.cover_image_url(query_title, record.year)
        except Exception:
            continue
        if not url:
            continue

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
        except Exception:
            continue

        ext = Path(urlparse(url).path).suffix or _DEFAULT_COVER_EXT
        dest_dir = covers_dir / record.id
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / f"cover{ext}").write_bytes(resp.content)

        record.cover_path = f"{record.id}/cover{ext}"
        record.metadata_source["cover_path"] = source.name
        return True
    return False
