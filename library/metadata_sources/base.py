"""Common interface for online metadata sources.

enrichment.py only depends on this interface, so adding another source later
(e.g. Comic Vine) doesn't require touching the orchestration logic.
"""
from __future__ import annotations

from typing import Protocol


class MetadataSource(Protocol):
    name: str

    def search(self, title: str, year: int | None = None) -> dict:
        """Best-effort lookup. Returns a partial ComicRecord field dict, or {} if not found."""
        ...

    def cover_image_url(self, title: str, year: int | None = None) -> str | None:
        """Best-effort lookup of a cover image URL, or None if not found."""
        ...
