from pathlib import Path

import pytest

from library.manual_attach import LinkAttachError
from library.models import ComicRecord
from library.quick_add import AddResult, QuickAddError, add_comic
from tests.test_physical_importer import FakeGoogleBooks, FakeMetron, FakeOpenLibrary


class FakeCoverResponse:
    content = b"fake-cover-bytes"

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _fake_cover_download(monkeypatch):
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())


def test_add_comic_from_comic_geeks_link_creates_new_record(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {
        "series": "Absolute Batman", "issue_number": "16", "publisher": "DC Comics", "year": 2026,
        "description": "A synopsis.", "author": "Scott Snyder", "upc": "76194138584601611",
        "_image_url": "https://example.com/cover.jpg",
    })
    records: dict[str, ComicRecord] = {}

    result = add_comic(
        records, "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", ["print"],
        metron=None, google_books=None, open_library=None, covers_dir=tmp_path,
    )

    assert isinstance(result, AddResult)
    assert result.merged is False
    assert result.record.type == "comic"
    assert result.record.title == "Absolute Batman #16"
    assert result.record.series == "Absolute Batman"
    assert result.record.publisher == "DC Comics"
    assert result.record.formats == ["print"]
    assert result.record.upc == "76194138584601611"
    assert result.record.id in records
    assert records[result.record.id] is result.record


def test_add_comic_from_comic_geeks_link_sets_title_to_series_only_when_no_issue_number(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {"series": "Some TPB"})
    records: dict[str, ComicRecord] = {}

    result = add_comic(
        records, "https://leagueofcomicgeeks.com/comic/1/some-tpb", ["digital"],
        metron=None, google_books=None, open_library=None, covers_dir=tmp_path,
    )

    assert result.record.title == "Some TPB"


def test_add_comic_from_comic_geeks_link_merges_into_existing_digital_record(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {
        "series": "Absolute Batman", "issue_number": "16",
    })
    records: dict[str, ComicRecord] = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="16", formats=["digital"],
        )
    }

    result = add_comic(
        records, "https://leagueofcomicgeeks.com/comic/1/absolute-batman-16", ["print"],
        metron=None, google_books=None, open_library=None, covers_dir=tmp_path,
    )

    assert result.merged is True
    assert result.record is records["d1"]
    assert records["d1"].formats == ["digital", "print"]
    assert len(records) == 1


def test_add_comic_from_unreadable_comic_geeks_link_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {})
    records: dict[str, ComicRecord] = {}

    with pytest.raises(QuickAddError):
        add_comic(
            records, "https://leagueofcomicgeeks.com/comic/999/nope", ["print"],
            metron=None, google_books=None, open_library=None, covers_dir=tmp_path,
        )


def test_add_comic_from_comic_geeks_link_handles_missing_series(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {
        "issue_number": "16",
    })
    records: dict[str, ComicRecord] = {}

    result = add_comic(
        records, "https://leagueofcomicgeeks.com/comic/1/something", ["print"],
        metron=None, google_books=None, open_library=None, covers_dir=tmp_path,
    )

    assert result.record.title == ""
    assert result.record.issue_number == "16"
    assert result.merged is False
    assert result.record.id in records


def test_add_comic_from_upc_routes_to_metron(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(upc_result={
        "series": {"name": "Absolute Batman"}, "number": "10",
        "desc": "A synopsis.", "credits": [],
    })

    result = add_comic(
        records, "76194138584601011", ["print"],
        metron=metron, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert metron.upc_calls == ["76194138584601011"]
    assert result.record.id == "upc-76194138584601011"
    assert result.record.upc == "76194138584601011"
    assert result.record.description == "A synopsis."
    assert result.record.formats == ["print"]


def test_add_comic_from_isbn_shaped_code_routes_to_open_library(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    open_library = FakeOpenLibrary(isbn_result={"author": "Frank Miller"})

    result = add_comic(
        records, "9781401207526", ["digital", "print"],
        metron=None, google_books=FakeGoogleBooks(), open_library=open_library, covers_dir=tmp_path,
    )

    assert result.record.id == "isbn-9781401207526"
    assert result.record.isbn == "9781401207526"
    assert result.record.author == "Frank Miller"
    assert result.record.formats == ["digital", "print"]


def test_add_comic_from_upc_with_no_metron_match_still_creates_bare_record(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(upc_result=None, search_result={})

    result = add_comic(
        records, "76194138584601011", ["print"],
        metron=metron, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.merged is False
    assert result.record.id == "upc-76194138584601011"
    assert result.record.title == "76194138584601011"


def test_add_comic_from_upc_merges_into_existing_digital_record(tmp_path: Path):
    records: dict[str, ComicRecord] = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="10", formats=["digital"],
        )
    }
    metron = FakeMetron(upc_result={"series": {"name": "Absolute Batman"}, "number": "10", "credits": []})

    result = add_comic(
        records, "76194138584601011", ["print"],
        metron=metron, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.merged is True
    assert records["d1"].formats == ["digital", "print"]
    assert records["d1"].upc == "76194138584601011"
    assert "upc-76194138584601011" not in records


def test_add_comic_rejects_unrecognized_input(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    with pytest.raises(QuickAddError):
        add_comic(
            records, "not a valid identifier", ["print"],
            metron=None, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path,
        )
