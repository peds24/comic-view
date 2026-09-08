"""Shared title/series normalization and digital-record matching helpers,
used by the physical importer (to avoid duplicating a comic/manga already
found by the digital scanner) and by enrichment's cover-source routing."""
from __future__ import annotations

import re

from library.models import ComicRecord

_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")
_ISSUE_RE = re.compile(r"#(\d+)")
_ISSUE_SUFFIX_RE = re.compile(r"\s*#\d+\s*$")
_TRAILING_VOL_RE = re.compile(r",?\s*Vol(?:ume)?\.?\s*(\d+)\s*$", re.IGNORECASE)
_TRAILING_NUMBER_RE = re.compile(r"\s+(\d{1,3})\s*$")

# Titles containing any of these are collected editions / variants — never
# attempted against a single-issue digital match, always print-only.
_NON_MATCHABLE_KEYWORDS = (
    "annual", "hc", "tp", "omnibus", "compendium", "special",
    "printing", "variant", "edition", "collection",
)


def normalize_series(raw: str) -> str:
    """Strips trailing parenthetical qualifiers a series name may carry —
    year ranges ("(2024 - Present)"), volume numbers ("(Vol. 4)"), a bare
    year ("(2026)"), edition notes ("(New Edition)"), etc. Applied
    repeatedly in case more than one trailing group is present."""
    series = (raw or "").strip()
    while True:
        stripped = _TRAILING_PAREN_RE.sub("", series).strip()
        if stripped == series:
            return series
        series = stripped


def normalize_issue(issue: str) -> str:
    if issue.isdigit():
        return str(int(issue))
    return issue


def extract_issue(full_title: str) -> str | None:
    """Comic issue number from a '#N' style title, e.g. "Batman #14"."""
    match = _ISSUE_RE.search(full_title or "")
    return match.group(1) if match else None


def extract_manga_issue(full_title: str) -> str | None:
    """Manga volumes don't use '#N' — they're 'Series, Vol. N' or end with
    a bare trailing number, e.g. "Attack on Titan 29"."""
    match = _TRAILING_VOL_RE.search(full_title or "")
    if not match:
        match = _TRAILING_NUMBER_RE.search(full_title or "")
    return match.group(1) if match else None


def strip_manga_volume_suffix(full_title: str) -> str:
    """Best-effort series name for a manga title with its volume suffix
    removed, e.g. "Attack on Titan, Vol. 29" -> "Attack on Titan"."""
    title = full_title or ""
    stripped = _TRAILING_VOL_RE.sub("", title).strip()
    if stripped != title:
        return stripped
    stripped = _TRAILING_NUMBER_RE.sub("", title).strip()
    return stripped or title


def strip_issue_suffix(full_title: str) -> str:
    """Best-effort series name for a single-issue title with its '#N'
    suffix removed, e.g. "Batman #14" -> "Batman"."""
    return _ISSUE_SUFFIX_RE.sub("", full_title or "").strip()


def is_matchable(full_title: str, issue_number: str | None) -> bool:
    if issue_number is None:
        return False
    lowered = (full_title or "").lower()
    return not any(keyword in lowered for keyword in _NON_MATCHABLE_KEYWORDS)


def _find_match(
    records: dict[str, ComicRecord], series: str, issue_number: str, required_format: str | None = None
) -> ComicRecord | None:
    target_series = (series or "").lower()
    target_issue = normalize_issue(issue_number)
    for record in records.values():
        if required_format and required_format not in record.formats:
            continue
        if (record.series or "").lower() != target_series:
            continue
        if record.issue_number is None:
            continue
        if normalize_issue(record.issue_number) != target_issue:
            continue
        return record
    return None


def find_digital_match(
    records: dict[str, ComicRecord], series: str, issue_number: str
) -> ComicRecord | None:
    return _find_match(records, series, issue_number, required_format="digital")


def find_matching_record(
    records: dict[str, ComicRecord], series: str, issue_number: str
) -> ComicRecord | None:
    """Like find_digital_match, but matches a record regardless of its
    current formats — used when adding a new format (digital or print) to
    a comic that might already exist in the *other* format, so a new add
    can merge into it instead of creating a duplicate id for the same
    issue."""
    return _find_match(records, series, issue_number)
