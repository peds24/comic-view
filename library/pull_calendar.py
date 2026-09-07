"""Parses League of Comic Geeks' per-user pull-list ICS calendar feed into
individual pulled comics, and tracks which calendar events have already
been processed by the weekly check-pulls run.

Each week's VEVENT bundles one or more titles (and their prices) into one
DESCRIPTION blob — there's no per-comic link here (confirmed live; see the
design doc), just enough text to resolve via title search
(pull_resolver.py)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from icalendar import Calendar

from library import browser_fetch

_PRICE_PREFIX = "$"
_TRAILER_PREFIX = "don't forget"


@dataclass
class PulledItem:
    event_uid: str
    release_date: date
    title: str
    price: str | None


def fetch_pulled_items(calendar_url: str) -> list[PulledItem]:
    """Fetches and parses the calendar at `calendar_url`. Returns [] if
    the feed can't be fetched at all."""
    raw = browser_fetch.download_text(calendar_url)
    if not raw:
        return []
    return parse_ics(raw)


def parse_ics(raw_ics: str) -> list[PulledItem]:
    calendar = Calendar.from_ical(raw_ics)
    items: list[PulledItem] = []
    for component in calendar.walk("VEVENT"):
        uid = str(component.get("UID"))
        release_date = component.get("DTSTART").dt
        description = str(component.get("DESCRIPTION") or "")
        items.extend(_parse_description(uid, release_date, description))
    return items


def _parse_description(uid: str, release_date: date, description: str) -> list[PulledItem]:
    lines = [line.strip() for line in description.split("\n")]
    items: list[PulledItem] = []
    pending_title: str | None = None

    def _flush(price: str | None) -> None:
        nonlocal pending_title
        if pending_title is not None:
            items.append(PulledItem(event_uid=uid, release_date=release_date, title=pending_title, price=price))
            pending_title = None

    for line in lines:
        if not line or line.lower().startswith(_TRAILER_PREFIX):
            continue
        if line.startswith(_PRICE_PREFIX):
            price = line if len(line) > 1 else None
            _flush(price)
            continue
        _flush(None)  # a title line with no price line before it — add it with no price
        pending_title = line
    _flush(None)
    return items


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"processed_uids": []}
    state = json.loads(path.read_text())
    state.setdefault("processed_uids", [])
    return state


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))
