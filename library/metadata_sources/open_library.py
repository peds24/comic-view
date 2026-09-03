"""Open Library API client — primary source for ISBN-coded items (see
enrichment routing in comic_geeks_importer.py), matching the routing
already proven in the longbox app (github.com/peds24/longbox): Open
Library first, Google Books as fallback only for what Open Library lacks.

Uses the `/api/books?bibkeys=...&jscmd=data` endpoint, not the bare
`/isbn/{isbn}.json` edition record — the bibkeys form returns title,
authors, publisher, publish date and a cover URL in one call; the bare
edition record has none of author/publisher/cover directly (they're a
separate hop through /works/ and /authors/). It has no description field
either way, which is why Google Books still runs as a second pass.
"""
from __future__ import annotations

from library.http_utils import get_with_retry

_BOOKS_URL = "https://openlibrary.org/api/books"


class OpenLibrarySource:
    name = "open_library"

    def lookup_isbn(self, isbn: str) -> dict:
        """Exact-edition lookup by ISBN-13/10. Returns a partial
        ComicRecord field dict (plus '_image_url' if a cover is available),
        or {} if this ISBN isn't in Open Library."""
        resp = get_with_retry(
            _BOOKS_URL, params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"}, timeout=10
        )
        resp.raise_for_status()
        book = resp.json().get(f"ISBN:{isbn}")
        if not book:
            return {}

        result: dict = {}
        if book.get("title"):
            result["title"] = book["title"]

        authors = book.get("authors")
        if authors:
            names = [a["name"] for a in authors if a.get("name")]
            if names:
                result["author"] = ", ".join(names)

        publishers = book.get("publishers")
        if publishers:
            names = [p["name"] for p in publishers if p.get("name")]
            if names:
                result["publisher"] = names[0]

        publish_date = book.get("publish_date")
        if publish_date:
            digits = "".join(c for c in publish_date if c.isdigit())
            if len(digits) >= 4:
                result["year"] = int(digits[:4])

        cover = book.get("cover") or {}
        image_url = cover.get("large") or cover.get("medium") or cover.get("small")
        if image_url:
            result["_image_url"] = image_url

        return result
