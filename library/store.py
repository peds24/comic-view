"""Load, merge, and save the library.json database.

This is the one place that reads/writes library.json. Merge rule: a new id
is appended; an existing id is left untouched, so a rescan never clobbers
`status` or any other field a previous scan/enrich pass (or the user) set.
"""
from __future__ import annotations

import json
from pathlib import Path

from library.models import ComicRecord


def load_library(path: Path) -> dict[str, ComicRecord]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {entry["id"]: ComicRecord.from_dict(entry) for entry in raw}


def save_library(path: Path, records: dict[str, ComicRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records.values(), key=lambda r: (r.series or r.title, r.issue_number or ""))
    path.write_text(json.dumps([r.to_dict() for r in ordered], indent=2))


def merge_record(records: dict[str, ComicRecord], new_record: ComicRecord) -> bool:
    """Add new_record if its id isn't already present. Returns True if added."""
    if new_record.id in records:
        return False
    records[new_record.id] = new_record
    return True


def delete_record(records: dict[str, ComicRecord], record_id: str) -> ComicRecord | None:
    """Removes and returns the record, or None if record_id isn't present."""
    return records.pop(record_id, None)
