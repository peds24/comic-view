"""Fill in missing ComicRecord fields using online metadata sources.

Metron is tried first (comics-focused), Google Books second (broader
coverage, better for manga). Idempotent: a record with no missing fields is
skipped unless force=True.
"""
from __future__ import annotations

from library.metadata_sources.base import MetadataSource
from library.models import ComicRecord


def enrich_record(record: ComicRecord, sources: list[MetadataSource], force: bool = False) -> bool:
    """Mutates record in place. Returns True if anything changed."""
    if not force and not record.missing_fields():
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
    return changed


def enrich_all(records: dict[str, ComicRecord], sources: list[MetadataSource], force: bool = False) -> int:
    updated = 0
    for record in records.values():
        if enrich_record(record, sources, force=force):
            updated += 1
    return updated
