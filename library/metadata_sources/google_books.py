"""Google Books API client — fallback metadata source, and the primary
source for ISBN-based physical manga import (see isbn_importer.py).

Broader catalog coverage than Metron, especially useful for manga volumes.
Works keyless at low request volume.
"""
from __future__ import annotations

import re

import requests

_BASE_URL = "https://www.googleapis.com/books/v1/volumes"


class GoogleBooksSource:
    name = "google_books"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    def search(self, title: str, year: int | None = None) -> dict:
        info = self._query(f"intitle:{title}")
        return self._parse_fields(info) if info else {}

    def cover_image_url(self, title: str, year: int | None = None) -> str | None:
        # The single best title match (items[0]) frequently has no cover even
        # when other editions of the same book do — scan several candidates.
        return self._find_image_among_candidates(f"intitle:{title}")

    def lookup_isbn(self, isbn: str) -> dict:
        """Exact-match lookup by ISBN-13. Returns a partial ComicRecord field
        dict (plus '_image_url' if a cover is available for this edition), or
        {} if not found."""
        info = self._query(f"isbn:{isbn}")
        if not info:
            return {}
        result = self._parse_fields(info)
        result["title"] = info.get("title")
        image_url = self._image_url(info)
        if image_url:
            result["_image_url"] = image_url
        return result

    def _query(self, q: str) -> dict | None:
        items = self._query_items(q)
        if not items:
            return None
        return items[0].get("volumeInfo", {})

    def _find_image_among_candidates(self, q: str, limit: int = 5) -> str | None:
        for item in self._query_items(q)[:limit]:
            url = self._image_url(item.get("volumeInfo", {}))
            if url:
                return url
        return None

    def _query_items(self, q: str) -> list[dict]:
        params = {"q": q}
        if self._api_key:
            params["key"] = self._api_key

        resp = requests.get(_BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json().get("items", [])

    @staticmethod
    def _image_url(info: dict) -> str | None:
        return info.get("imageLinks", {}).get("thumbnail")

    @staticmethod
    def _parse_fields(info: dict) -> dict:
        result: dict = {}

        authors = info.get("authors")
        if authors:
            result["author"] = ", ".join(authors)

        publisher = info.get("publisher")
        if publisher:
            result["publisher"] = publisher

        description = info.get("description")
        if description:
            result["description"] = description

        published_date = info.get("publishedDate")
        if published_date:
            match = re.match(r"(\d{4})", published_date)
            if match:
                result["year"] = int(match.group(1))

        return result
