from pathlib import Path

import pytest

from library.manual_attach import LinkAttachError
from library.models import ComicRecord
from library.quick_add import AddResult, QuickAddError, add_comic, add_manga
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


def test_add_manga_from_isbn_routes_to_open_library(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    open_library = FakeOpenLibrary(isbn_result={"author": "Hajime Isayama"})

    result = add_manga(
        records, "9781632368287", ["print"],
        google_books=FakeGoogleBooks(), open_library=open_library, covers_dir=tmp_path,
    )

    assert result.record.id == "isbn-9781632368287"
    assert result.record.isbn == "9781632368287"
    assert result.record.type == "manga"
    assert result.record.author == "Hajime Isayama"


def test_add_manga_from_title_searches_google_books(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    google_books = FakeGoogleBooks()
    google_books.search_result = {"author": "Hajime Isayama", "description": "Titans."}
    google_books.cover_result = "https://example.com/cover.jpg"

    result = add_manga(
        records, "Attack on Titan, Vol. 29", ["digital"],
        google_books=google_books, open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.record.type == "manga"
    assert result.record.title == "Attack on Titan, Vol. 29"
    assert result.record.series == "Attack on Titan"
    assert result.record.issue_number == "29"
    assert result.record.author == "Hajime Isayama"
    assert result.record.description == "Titans."
    assert result.record.id.startswith("manual-attack-on-titan-vol-29-")


def test_add_manga_from_title_with_no_search_results_still_creates_bare_record(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    google_books = FakeGoogleBooks()

    result = add_manga(
        records, "Some Obscure Title", ["print"],
        google_books=google_books, open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.merged is False
    assert result.record.title == "Some Obscure Title"
    assert result.record.author is None


def test_add_manga_from_title_merges_into_existing_digital_record(tmp_path: Path):
    """Merging needs a series + issue number to match against — a bare ISBN
    has no title text to derive those from (`enrich_isbn`, like the batch
    importer, never fills series/issue_number, only author/publisher/year/
    description), so only the title path can ever merge. This is a real
    limitation of ISBN-only quick-add input, not an oversight: if the owner
    wants a merge, typing the title (or fixing it up afterward in
    viewer.html) is the way."""
    records: dict[str, ComicRecord] = {
        "d1": ComicRecord(
            id="d1", title="Attack on Titan, Vol. 29", type="manga", series="Attack on Titan",
            issue_number="29", formats=["digital"],
        )
    }
    google_books = FakeGoogleBooks()
    google_books.search_result = {"author": "Hajime Isayama"}

    result = add_manga(
        records, "Attack on Titan, Vol. 29", ["print"],
        google_books=google_books, open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.merged is True
    assert result.record is records["d1"]
    assert records["d1"].formats == ["digital", "print"]
    assert len(records) == 1


def test_add_manga_from_bare_isbn_never_merges_since_no_title_to_match_on(tmp_path: Path):
    records: dict[str, ComicRecord] = {
        "d1": ComicRecord(
            id="d1", title="Attack on Titan, Vol. 29", type="manga", series="Attack on Titan",
            issue_number="29", formats=["digital"],
        )
    }
    open_library = FakeOpenLibrary(isbn_result={"author": "Hajime Isayama"})

    result = add_manga(
        records, "9781632368287", ["print"],
        google_books=FakeGoogleBooks(), open_library=open_library, covers_dir=tmp_path,
    )

    assert result.merged is False
    assert records["d1"].formats == ["digital"]  # untouched
    assert records["isbn-9781632368287"].isbn == "9781632368287"


def test_add_manga_from_title_handles_google_books_search_exception(tmp_path: Path):
    """Google Books API can error out (e.g., 429 rate limit). The title-search
    path should gracefully fall back to a bare record, not propagate the exception."""
    records: dict[str, ComicRecord] = {}
    google_books = FakeGoogleBooks()

    # Mock search to raise an exception
    def raise_on_search(title, year=None):
        raise Exception("Google Books API error: 429 Too Many Requests")
    google_books.search = raise_on_search

    result = add_manga(
        records, "Attack on Titan, Vol. 29", ["print"],
        google_books=google_books, open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    # Should still return a record with parsed series/issue, just no enrichment
    assert result.merged is False
    assert result.record.title == "Attack on Titan, Vol. 29"
    assert result.record.series == "Attack on Titan"
    assert result.record.issue_number == "29"
    assert result.record.author is None  # not enriched due to exception
    assert result.record.id in records


def test_add_manga_from_title_handles_cover_image_url_exception(tmp_path: Path):
    """Cover image lookup can also error out. Should degrade gracefully."""
    records: dict[str, ComicRecord] = {}
    google_books = FakeGoogleBooks()
    google_books.search_result = {"author": "Hajime Isayama"}

    # Mock cover_image_url to raise an exception
    def raise_on_cover(title, year=None):
        raise Exception("Google Books API error: network timeout")
    google_books.cover_image_url = raise_on_cover

    result = add_manga(
        records, "Attack on Titan, Vol. 29", ["print"],
        google_books=google_books, open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    # Should still return enriched record (search worked), just no cover
    assert result.merged is False
    assert result.record.author == "Hajime Isayama"
    assert result.record.cover_path is None  # not downloaded due to exception
    assert result.record.id in records
