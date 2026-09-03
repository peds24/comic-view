"""Google Books API client — fallback metadata source.

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
        params = {"q": f"intitle:{title}"}
        if self._api_key:
            params["key"] = self._api_key

        resp = requests.get(_BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return {}

        info = items[0].get("volumeInfo", {})
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
