"""Manually attach a cover image, or a specific Comic Geeks issue, to an
existing record — for cases the automatic importer can't resolve on its
own (a printing/variant Metron's UPC index doesn't have, or any record
still missing a cover). Used by the write endpoints `comic-library serve`
exposes for viewer.html's per-card attach controls.
"""
from __future__ import annotations

from pathlib import Path

from library.covers import download_cover, save_cover_bytes
from library.metadata_sources import comic_geeks
from library.models import ComicRecord

_OVERWRITE_FIELDS = ("series", "issue_number", "publisher", "year", "description", "author")


class LinkAttachError(Exception):
    """Raised when a Comic Geeks URL can't be resolved to a specific issue."""


def attach_cover_bytes(record: ComicRecord, data: bytes, ext: str, covers_dir: Path) -> None:
    """Saves `data` as this record's cover, overwriting any existing one."""
    save_cover_bytes(record, data, ext, "manual", covers_dir)


def set_title(record: ComicRecord, title: str) -> None:
    """Overwrites this record's title with a manually-edited value."""
    record.title = title
    record.metadata_source["title"] = "manual"


def set_year(record: ComicRecord, year: int | None) -> None:
    """Overwrites this record's year with a manually-edited value, or clears
    it (and its source) back to unknown if year is None."""
    record.year = year
    if year is None:
        record.metadata_source.pop("year", None)
    else:
        record.metadata_source["year"] = "manual"


def set_formats(record: ComicRecord, formats: list[str]) -> None:
    """Overwrites this record's formats (e.g. correcting a digital scan
    that's actually also owned in print, or vice versa)."""
    record.formats = formats


def _overwrite(record: ComicRecord, field: str, value, source_name: str) -> None:
    if value:
        setattr(record, field, value)
        record.metadata_source[field] = source_name


def attach_comic_geeks_issue(record: ComicRecord, url: str, covers_dir: Path) -> None:
    """Overwrites series/issue_number/publisher/year/description/author/
    cover/upc from the Comic Geeks issue at `url` — `title` is left
    untouched, since it carries printing/variant information (e.g.
    "2nd Printing") specific to the physical copy owned, which the base
    issue's page doesn't capture. Raises LinkAttachError if the page can't
    be read."""
    info = comic_geeks.fetch_issue(url)
    if not info:
        raise LinkAttachError(f"Couldn't read a Comic Geeks issue from: {url!r}")

    for field in _OVERWRITE_FIELDS:
        _overwrite(record, field, info.get(field), "comic_geeks")
    # Comic Geeks gives each printing/variant its own page with its own
    # UPC, so this is trustworthy as long as the user pasted the link for
    # their specific copy.
    if info.get("upc"):
        _overwrite(record, "upc", info["upc"], "comic_geeks")

    if info.get("_image_url"):
        download_cover(record, info["_image_url"], "comic_geeks", covers_dir)


def attach_from_link(record: ComicRecord, url: str, *, covers_dir: Path) -> None:
    """Attaches metadata from a Comic Geeks issue link. Raises
    LinkAttachError if the URL isn't a leagueofcomicgeeks.com link, or if
    the page can't be read."""
    if not comic_geeks.is_comic_geeks_url(url):
        raise LinkAttachError(f"Only leagueofcomicgeeks.com links are supported: {url!r}")
    attach_comic_geeks_issue(record, url, covers_dir)
