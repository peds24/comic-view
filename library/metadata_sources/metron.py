"""Metron (https://metron.cloud) API client — comics-focused metadata.

Requires a free Metron account (HTTP Basic Auth). Best coverage for Western
comics; used as the first enrichment source.
"""
from __future__ import annotations

import requests

_BASE_URL = "https://metron.cloud/api"


class MetronSource:
    name = "metron"

    def __init__(self, username: str, password: str):
        self._auth = (username, password)

    def search(self, title: str, year: int | None = None) -> dict:
        series = self._find_series(title)
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
            cover_date = issue.get("cover_date")
            if cover_date and len(cover_date) >= 4 and cover_date[:4].isdigit():
                result["year"] = int(cover_date[:4])
            writer = self._extract_writer(issue)
            if writer:
                result["author"] = writer

        return result

    def _find_series(self, title: str) -> dict | None:
        resp = requests.get(
            f"{_BASE_URL}/series/",
            params={"name": title},
            auth=self._auth,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None

    def _find_issue(self, series_id: int, year: int | None) -> dict | None:
        params = {"series_id": series_id}
        resp = requests.get(f"{_BASE_URL}/issue/", params=params, auth=self._auth, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        if year:
            for candidate in results:
                cover_date = candidate.get("cover_date", "")
                if cover_date.startswith(str(year)):
                    return self._issue_detail(candidate["id"])
        return self._issue_detail(results[0]["id"])

    def _issue_detail(self, issue_id: int) -> dict:
        resp = requests.get(f"{_BASE_URL}/issue/{issue_id}/", auth=self._auth, timeout=10)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _extract_writer(issue: dict) -> str | None:
        for credit in issue.get("credits", []):
            roles = [r.get("name", "") for r in credit.get("role", [])]
            if any(role.lower() == "writer" for role in roles):
                return credit.get("creator")
        return None
