"""Manually attach a cover image, or a specific Metron/Comic Geeks issue,
to an existing record — for cases the automatic importer can't resolve on
its own (a printing/variant Metron's UPC index doesn't have, or any record
still missing a cover). Used by the write endpoints `comic-library serve`
exposes for viewer.html's per-card attach controls.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from library.covers import download_cover, save_cover_bytes
from library.metadata_sources import comic_geeks
from library.metadata_sources.metron import MetronSource, year_from_issue
from library.models import ComicRecord

_OVERWRITE_FIELDS = ("series", "issue_number", "publisher", "year", "description", "author")


class LinkAttachError(Exception):
    """Raised when a Metron/Comic Geeks URL can't be resolved to a specific issue."""


def attach_cover_bytes(record: ComicRecord, data: bytes, ext: str, covers_dir: Path) -> None:
    """Saves `data` as this record's cover, overwriting any existing one."""
    save_cover_bytes(record, data, ext, "manual", covers_dir)


def _overwrite(record: ComicRecord, field: str, value, source_name: str) -> None:
    if value:
        setattr(record, field, value)
        record.metadata_source[field] = source_name


def _parse_metron_url(url: str) -> int | tuple[str, str, int | None]:
    """Returns either a numeric Metron issue id, or (series, number, year)
    parsed from a metron.cloud issue-page slug like
    "absolute-batman-2024-16" -> ("absolute batman", "16", 2024).

    Metron's website uses a slug (not the numeric API id) in its issue
    URLs — confirmed against a live issue's own `resource_url` field — and
    the site is behind bot protection that blocks scraping the page for
    the real id, so a slug URL is resolved via the same series+number+year
    lookup the automatic importer already uses, not by fetching the page.
    """
    segment = urlparse(url).path.strip("/").rsplit("/", 1)[-1]
    if segment.isdigit():
        return int(segment)

    parts = [p for p in segment.split("-") if p]
    if len(parts) < 2:
        raise LinkAttachError(f"Couldn't parse a Metron issue from: {url!r}")

    number = parts[-1]
    if len(parts) >= 3 and len(parts[-2]) == 4 and parts[-2].isdigit():
        year: int | None = int(parts[-2])
        series = " ".join(parts[:-2])
    else:
        year = None
        series = " ".join(parts[:-1])

    if not series:
        raise LinkAttachError(f"Couldn't parse a Metron issue from: {url!r}")
    return series, number, year


def attach_metron_issue(record: ComicRecord, metron: MetronSource, url: str, covers_dir: Path) -> None:
    """Overwrites series/issue_number/publisher/year/description/author/
    cover from the Metron issue at `url` — `title` is left untouched,
    since it carries printing/variant information (e.g. "2nd Printing")
    specific to the physical copy owned, which the base issue Metron has
    on file doesn't capture. Raises LinkAttachError if the link can't be
    resolved to an issue."""
    parsed = _parse_metron_url(url)
    if isinstance(parsed, int):
        issue = metron.get_issue_by_id(parsed)
    else:
        series, number, year = parsed
        issue = metron.find_issue_by_series_and_number(series, number, year)
    if not issue:
        raise LinkAttachError(f"Metron has no matching issue for: {url!r}")

    series_info = issue.get("series")
    publisher_info = issue.get("publisher")
    fields = {
        "series": series_info.get("name") if isinstance(series_info, dict) else None,
        "issue_number": issue.get("number"),
        "publisher": publisher_info.get("name") if isinstance(publisher_info, dict) else None,
        "year": year_from_issue(issue),
        "description": issue.get("desc"),
        "author": MetronSource._extract_writer(issue),
    }
    for field in _OVERWRITE_FIELDS:
        _overwrite(record, field, fields.get(field), "metron")

    if issue.get("image"):
        download_cover(record, issue["image"], "metron", covers_dir)


def attach_comic_geeks_issue(record: ComicRecord, url: str, covers_dir: Path) -> None:
    """Overwrites series/issue_number/publisher/year/description/author/
    cover/upc from the Comic Geeks issue at `url` — `title` is left
    untouched, same reasoning as attach_metron_issue. Raises
    LinkAttachError if the page can't be read."""
    info = comic_geeks.fetch_issue(url)
    if not info:
        raise LinkAttachError(f"Couldn't read a Comic Geeks issue from: {url!r}")

    for field in _OVERWRITE_FIELDS:
        _overwrite(record, field, info.get(field), "comic_geeks")
    # Comic Geeks gives each printing/variant its own page with its own
    # UPC, so this is trustworthy as long as the user pasted the link for
    # their specific copy — unlike Metron, which only has the base
    # issue's UPC and would silently clobber the variant's real barcode.
    if info.get("upc"):
        _overwrite(record, "upc", info["upc"], "comic_geeks")

    if info.get("_image_url"):
        download_cover(record, info["_image_url"], "comic_geeks", covers_dir)


def attach_from_link(record: ComicRecord, url: str, *, metron: MetronSource | None, covers_dir: Path) -> None:
    """Attaches metadata from either a Metron or a Comic Geeks issue link,
    auto-detected by URL. Raises LinkAttachError if the link can't be
    resolved, or if it's a Metron link and Metron isn't configured."""
    if comic_geeks.is_comic_geeks_url(url):
        attach_comic_geeks_issue(record, url, covers_dir)
        return

    if metron is None:
        raise LinkAttachError("Metron isn't configured in config.yaml.")
    attach_metron_issue(record, metron, url, covers_dir)
