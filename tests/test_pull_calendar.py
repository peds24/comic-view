from datetime import date
from pathlib import Path

from library.pull_calendar import PulledItem, fetch_pulled_items, load_state, parse_ics, save_state

# A trimmed real fragment of the pull-list ICS feed's structure, matching
# what was confirmed against the live feed this session.
_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//hacksw/handcal//NONSGML v1.0//EN
CALSCALE:GREGORIAN
X-WR-CALNAME:My Comic Pulls
BEGIN:VEVENT
UID:single-issue-uid@cg
DTSTAMP:20260907T123050
DESCRIPTION:Batman #14\\n$4.99\\n\\nDon't forget to add these comics on League of Comic Geeks after.
SUMMARY:New Comics for 10/07
DTSTART;VALUE=DATE:20261007
END:VEVENT
BEGIN:VEVENT
UID:bundled-uid@cg
DTSTAMP:20260907T123050
DESCRIPTION:Batman #423 Facsimile Edition 2026\\n$3.99\\n\\nMidnight Spider-Man #1\\n$5.99\\n\\nDon't forget to add these comics on League of Comic Geeks after.
SUMMARY:New Comics for 10/07
DTSTART;VALUE=DATE:20261007
END:VEVENT
BEGIN:VEVENT
UID:blank-price-uid@cg
DTSTAMP:20260907T123050
DESCRIPTION:Absolute Batman #24\\n$4.99\\n\\nAbsolute Batman #24 Skottie Young Webstore Variant\\n$\\n\\nDon't forget to add these comics on League of Comic Geeks after.
SUMMARY:New Comics for 09/23
DTSTART;VALUE=DATE:20260923
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_single_title_event():
    items = parse_ics(_ICS)
    single = [i for i in items if i.event_uid == "single-issue-uid@cg"]
    assert single == [PulledItem(event_uid="single-issue-uid@cg", release_date=date(2026, 10, 7), title="Batman #14", price="$4.99")]


def test_parse_ics_bundled_titles_event():
    items = parse_ics(_ICS)
    bundled = [i for i in items if i.event_uid == "bundled-uid@cg"]
    assert bundled == [
        PulledItem(event_uid="bundled-uid@cg", release_date=date(2026, 10, 7), title="Batman #423 Facsimile Edition 2026", price="$3.99"),
        PulledItem(event_uid="bundled-uid@cg", release_date=date(2026, 10, 7), title="Midnight Spider-Man #1", price="$5.99"),
    ]


def test_parse_ics_blank_price_treated_as_none():
    items = parse_ics(_ICS)
    blank = [i for i in items if i.event_uid == "blank-price-uid@cg"]
    assert blank == [
        PulledItem(event_uid="blank-price-uid@cg", release_date=date(2026, 9, 23), title="Absolute Batman #24", price="$4.99"),
        PulledItem(event_uid="blank-price-uid@cg", release_date=date(2026, 9, 23), title="Absolute Batman #24 Skottie Young Webstore Variant", price=None),
    ]


def test_fetch_pulled_items_downloads_then_parses(monkeypatch):
    monkeypatch.setattr("library.pull_calendar.browser_fetch.download_text", lambda url, **kwargs: _ICS)
    items = fetch_pulled_items("https://leagueofcomicgeeks.com/member/calendar_ics/peds24")
    assert len(items) == 5


def test_fetch_pulled_items_returns_empty_list_on_download_failure(monkeypatch):
    monkeypatch.setattr("library.pull_calendar.browser_fetch.download_text", lambda url, **kwargs: "")
    assert fetch_pulled_items("https://leagueofcomicgeeks.com/member/calendar_ics/peds24") == []


def test_load_state_returns_empty_when_file_missing(tmp_path: Path):
    assert load_state(tmp_path / "pull_state.json") == {"processed_uids": []}


def test_save_state_then_load_state_round_trips(tmp_path: Path):
    path = tmp_path / "nested" / "pull_state.json"
    save_state(path, {"processed_uids": ["a@cg", "b@cg"]})
    assert load_state(path) == {"processed_uids": ["a@cg", "b@cg"]}
