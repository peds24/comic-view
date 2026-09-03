"""Metron (https://metron.cloud) API client — comics-focused metadata.

Requires a free Metron account (HTTP Basic Auth). Best coverage for Western
comics; used as the first enrichment source.
"""
from __future__ import annotations

from library.matching import normalize_series
from library.http_utils import get_with_retry

_BASE_URL = "https://metron.cloud/api"


def year_from_issue(issue: dict) -> int | None:
    """The store date (when the issue actually shipped) rather than the
    cover date (a nominal, often several-months-later publisher
    convention) is used as the release year."""
    store_date = issue.get("store_date") or ""
    if len(store_date) >= 4 and store_date[:4].isdigit():
        return int(store_date[:4])
    return None


class MetronSource:
    name = "metron"

    def __init__(self, username: str, password: str):
        self._auth = (username, password)

    def search(self, title: str, year: int | None = None) -> dict:
        series = self._find_series(title, year)
        if series is None:
            return {}

        result: dict = {}
        publisher = series.get("publisher", {}).get("name")
        if publisher:
            result["publisher"] = publisher

        issue = self._find_issue(series["id"], year)
        if issue:
            if issue.get("desc"):
                result["description"] = issue["desc"]
            issue_year = year_from_issue(issue)
            if issue_year:
                result["year"] = issue_year
            writer = self._extract_writer(issue)
            if writer:
                result["author"] = writer

        return result

    def cover_image_url(self, title: str, year: int | None = None) -> str | None:
        series = self._find_series(title, year)
        if series is None:
            return None
        issue = self._find_issue(series["id"], year)
        return issue.get("image") if issue else None

    def find_issue_by_upc(self, upc: str) -> dict | None:
        """Exact issue lookup by UPC/barcode — Metron's `/issue/?upc=` filter
        matches a single specific printing, so this is far more reliable than
        title search when a real barcode is available. Returns the full issue
        detail dict (same shape as _issue_detail), or None if no match."""
        resp = get_with_retry(f"{_BASE_URL}/issue/", params={"upc": upc}, auth=self._auth, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        return self._issue_detail(results[0]["id"])

    def find_issue_by_series_and_number(self, series: str, number: str, year: int | None = None) -> dict | None:
        """Exact issue lookup by series name + issue number (Metron's
        `/issue/?series_id=&number=`) — for an ongoing series, title+year
        alone (see `search`/`cover_image_url`) can't tell issue #14 from
        issue #22, since a year can span many issues. This can, as long as
        the issue number parses the same way Metron stores it (a bare
        string match, e.g. "14" — not "14A" variant suffixes). `year`
        disambiguates between multiple *volumes* sharing the same series
        name (e.g. "Batman" has run as four different Metron series across
        different eras, all named plain "Batman")."""
        series_result = self._find_series(series, year)
        if series_result is None:
            return None
        resp = get_with_retry(
            f"{_BASE_URL}/issue/",
            params={"series_id": series_result["id"], "number": number},
            auth=self._auth,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        return self._issue_detail(results[0]["id"])

    def _find_series(self, title: str, year: int | None = None) -> dict | None:
        """Metron's `name` filter is a substring/relevance search, not an
        exact match — searching "Batman" can return "Absolute Batman" as
        the top hit among hundreds of matches (confirmed against the live
        API). Prefer a result whose name exactly matches `title` (ignoring
        Metron's trailing "(YYYY)" year suffix); among several exact
        matches — a series name reused across eras, e.g. "Batman" (1940),
        (2011), (2016), (2025) are four different Metron series — prefer
        the one whose year range contains `year`. Only falls back to
        Metron's own top relevance match when no exact name match exists at
        all."""
        resp = get_with_retry(
            f"{_BASE_URL}/series/",
            params={"name": title},
            auth=self._auth,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None

        target = title.strip().lower()
        exact = [s for s in results if normalize_series(s.get("series", "")).lower() == target]
        if not exact:
            return results[0]
        if len(exact) == 1 or not year:
            return exact[0]
        for s in exact:
            began = s.get("year_began")
            ended = s.get("year_end") or 9999
            if began and began <= year <= ended:
                return s
        return exact[0]

    def _find_issue(self, series_id: int, year: int | None) -> dict | None:
        params = {"series_id": series_id}
        resp = get_with_retry(f"{_BASE_URL}/issue/", params=params, auth=self._auth, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        if year:
            for candidate in results:
                store_date = candidate.get("store_date", "")
                if store_date.startswith(str(year)):
                    return self._issue_detail(candidate["id"])
        return self._issue_detail(results[0]["id"])

    def _issue_detail(self, issue_id: int) -> dict:
        resp = get_with_retry(f"{_BASE_URL}/issue/{issue_id}/", auth=self._auth, timeout=10)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _extract_writer(issue: dict) -> str | None:
        """All credited writers, deduped and comma-joined — matches the
        longbox app's creditsToAuthor (github.com/peds24/longbox), which
        collects every writer instead of stopping at the first one found."""
        credits = issue.get("credits", [])
        writers = [
            c["creator"]
            for c in credits
            if c.get("creator") and any(r.get("name", "").lower() == "writer" for r in c.get("role", []))
        ]
        names = list(dict.fromkeys(writers))  # dedupe, keep first-seen order
        return ", ".join(names) if names else None
