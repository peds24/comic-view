"""Turns one pulled-list line item (a title + price parsed from the
League of Comic Geeks pull-list calendar, see pull_calendar.py) into a
new physical ComicRecord, merging into a matching digital record instead
of duplicating one where possible — mirrors physical_importer.py's merge
behavior for the Excel import path. Never guesses at an ambiguous series
match (see MetronSource.find_issue_confident) — those get reported back
for the user to resolve manually via add-comic instead."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from library.matching import extract_issue, find_matching_record, is_matchable, strip_issue_suffix
from library.metadata_sources.metron import MetronSource, apply_metron_issue
from library.models import ComicRecord
from library.pull_calendar import PulledItem

ResolverOutcome = Literal["added", "merged", "flagged"]


@dataclass
class ResolveResult:
    outcome: ResolverOutcome
    title: str
    reason: str | None = None
    candidates: list[dict] | None = None


def _slugify(text: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    return "-".join(keep.split()) or "untitled"


def resolve_and_add(
    item: PulledItem,
    records: dict[str, ComicRecord],
    metron: MetronSource,
    covers_dir: Path,
) -> ResolveResult:
    issue_number = extract_issue(item.title)

    if is_matchable(item.title, issue_number):
        series_guess = strip_issue_suffix(item.title)
        issue, status, candidates = metron.find_issue_confident(series_guess, issue_number, item.release_date.year)

        if status == "ambiguous":
            return ResolveResult(
                "flagged", item.title,
                reason=f"multiple Metron series named '{series_guess}' have issue #{issue_number}",
                candidates=candidates,
            )
        if status == "not_found":
            return ResolveResult(
                "flagged", item.title,
                reason=f"no Metron series named '{series_guess}' has issue #{issue_number}",
            )

        record_id = f"upc-{issue['upc']}" if issue.get("upc") else f"metron-{issue['id']}"
        record = ComicRecord(id=record_id, title=item.title, type="comic", issue_number=issue_number, formats=["print"])
        apply_metron_issue(record, issue, covers_dir)

        match = None
        if record.series and record.issue_number and is_matchable(record.title, record.issue_number):
            match = find_matching_record(records, record.series, record.issue_number)
        if match is not None:
            if "print" not in match.formats:
                match.formats.append("print")
            return ResolveResult("merged", item.title)

        records[record.id] = record
        return ResolveResult("added", item.title)

    # Collected edition / variant / annual / unmatchable title — best-effort
    # title search only; matching.is_matchable already excludes these from
    # ever being attempted as a single-issue match.
    partial = metron.search(item.title, item.release_date.year)
    if not partial:
        return ResolveResult("flagged", item.title, reason="no Metron match for this title")

    record = ComicRecord(
        id=f"pull-{item.release_date.isoformat()}-{_slugify(item.title)}",
        title=item.title, type="comic", issue_number=issue_number, formats=["print"],
    )
    record.apply_partial(partial, "metron")
    records[record.id] = record
    return ResolveResult("added", item.title)
