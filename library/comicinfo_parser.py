"""Parse the ComicInfo.xml schema (written by ComicRack, ComicTagger, etc.)
into the subset of fields our ComicRecord cares about.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

# Preference order for filling the "author" field from creator tags.
_CREATOR_TAGS = ("Writer", "Penciller", "Inker", "CoverArtist", "Letterer", "Colorist")


def parse_comicinfo(xml_bytes: bytes) -> dict:
    """Returns a partial dict of ComicRecord fields. Missing tags are omitted."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}

    def text(tag: str) -> str | None:
        el = root.find(tag)
        if el is None or el.text is None:
            return None
        value = el.text.strip()
        return value or None

    result: dict = {}

    title = text("Title")
    if title:
        result["title"] = title

    series = text("Series")
    if series:
        result["series"] = series

    number = text("Number")
    if number:
        result["issue_number"] = number

    publisher = text("Publisher")
    if publisher:
        result["publisher"] = publisher

    summary = text("Summary")
    if summary:
        result["description"] = summary

    year = text("Year")
    if year and year.isdigit():
        result["year"] = int(year)

    isbn = text("GTIN")
    if isbn:
        result["isbn"] = isbn

    author = None
    for tag in _CREATOR_TAGS:
        value = text(tag)
        if value:
            author = value
            break
    if author:
        result["author"] = author

    return result
