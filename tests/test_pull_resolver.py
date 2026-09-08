from datetime import date
from pathlib import Path

import pytest

from library.models import ComicRecord
from library.pull_calendar import PulledItem
from library.pull_resolver import resolve_and_add


class FakeMetron:
    def __init__(self, confident_result=None, search_result=None):
        self.confident_result = confident_result or (None, "not_found", [])
        self.search_result = search_result or {}
        self.confident_calls = []
        self.search_calls = []

    def find_issue_confident(self, series, number, year=None):
        self.confident_calls.append((series, number, year))
        return self.confident_result

    def search(self, title, year=None):
        self.search_calls.append((title, year))
        return self.search_result


class FakeCoverResponse:
    content = b"fake-cover-bytes"

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _fake_cover_download(monkeypatch):
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())


def _item(title="Batman #13", price="$4.99", release_date=date(2026, 10, 7), uid="uid@cg"):
    return PulledItem(event_uid=uid, release_date=release_date, title=title, price=price)


def test_resolve_and_add_creates_new_print_record_on_confident_match(tmp_path: Path):
    issue = {"id": 999, "series": {"name": "Batman"}, "number": "13", "store_date": "2026-10-07"}
    metron = FakeMetron(confident_result=(issue, "ok", []))
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(), records, metron, tmp_path)

    assert result.outcome == "added"
    assert metron.confident_calls == [("Batman", "13", 2026)]
    record = records["metron-999"]
    assert record.title == "Batman #13"
    assert record.formats == ["print"]
    assert record.series == "Batman"


def test_resolve_and_add_uses_upc_id_when_metron_issue_has_one(tmp_path: Path):
    issue = {"id": 999, "upc": "76194138584601011", "series": {"name": "Batman"}, "number": "13"}
    metron = FakeMetron(confident_result=(issue, "ok", []))
    records: dict[str, ComicRecord] = {}

    resolve_and_add(_item(), records, metron, tmp_path)

    assert "upc-76194138584601011" in records
    assert "metron-999" not in records


def test_resolve_and_add_merges_into_existing_digital_record(tmp_path: Path):
    issue = {"id": 999, "series": {"name": "Batman"}, "number": "13"}
    metron = FakeMetron(confident_result=(issue, "ok", []))
    records = {
        "d1": ComicRecord(id="d1", title="Batman", type="comic", series="Batman", issue_number="13", formats=["digital"]),
    }

    result = resolve_and_add(_item(), records, metron, tmp_path)

    assert result.outcome == "merged"
    assert records["d1"].formats == ["digital", "print"]
    assert len(records) == 1  # no second record created


def test_resolve_and_add_flags_ambiguous_series(tmp_path: Path):
    candidates = [{"series_id": 2481, "series_name": "Batman (1940)", "publisher": "DC Comics", "year_began": 1940, "year_end": 2011}]
    metron = FakeMetron(confident_result=(None, "ambiguous", candidates))
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(), records, metron, tmp_path)

    assert result.outcome == "flagged"
    assert "Batman" in result.reason
    assert result.candidates == candidates
    assert records == {}


def test_resolve_and_add_flags_when_series_not_found(tmp_path: Path):
    metron = FakeMetron(confident_result=(None, "not_found", []))
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(), records, metron, tmp_path)

    assert result.outcome == "flagged"
    assert records == {}


def test_resolve_and_add_best_effort_search_for_collected_edition(tmp_path: Path):
    metron = FakeMetron(search_result={"publisher": "Kodansha", "year": 2026, "description": "A synopsis."})
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(title="Billy Bat Vol. 2 TP", price="$13.99"), records, metron, tmp_path)

    assert result.outcome == "added"
    assert metron.search_calls == [("Billy Bat Vol. 2 TP", 2026)]
    record = records["pull-2026-10-07-billy-bat-vol-2-tp"]
    assert record.publisher == "Kodansha"
    assert record.formats == ["print"]


def test_resolve_and_add_flags_collected_edition_with_no_metron_match(tmp_path: Path):
    metron = FakeMetron(search_result={})
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(title="Billy Bat Vol. 2 TP", price="$13.99"), records, metron, tmp_path)

    assert result.outcome == "flagged"
    assert records == {}
