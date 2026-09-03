from pathlib import Path

import openpyxl
import pytest

from library.models import ComicRecord
from library.physical_importer import import_physical_xlsx


class FakeMetron:
    def __init__(self, upc_result=None, search_result=None, cover_url=None, series_number_result=None):
        self.upc_result = upc_result
        self.search_result = search_result or {}
        self.cover_url = cover_url
        self.series_number_result = series_number_result
        self.upc_calls = []
        self.search_calls = []
        self.series_number_calls = []

    def find_issue_by_upc(self, upc):
        self.upc_calls.append(upc)
        return self.upc_result

    def find_issue_by_series_and_number(self, series, number, year=None):
        self.series_number_calls.append((series, number))
        return self.series_number_result

    def search(self, title, year=None):
        self.search_calls.append((title, year))
        return self.search_result

    def cover_image_url(self, title, year=None):
        return self.cover_url


class FakeGoogleBooks:
    def __init__(self, isbn_result=None):
        self.isbn_result = isbn_result or {}
        self.calls = []

    def lookup_isbn(self, isbn):
        self.calls.append(isbn)
        return self.isbn_result


class FakeOpenLibrary:
    def __init__(self, isbn_result=None):
        self.isbn_result = isbn_result or {}
        self.calls = []

    def lookup_isbn(self, isbn):
        self.calls.append(isbn)
        return self.isbn_result


class FakeCoverResponse:
    def __init__(self, content=b"fake-image-bytes"):
        self.content = content

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _fake_cover_download(monkeypatch):
    monkeypatch.setattr(
        "library.covers.get_with_retry",
        lambda *a, **k: FakeCoverResponse(),
    )


def make_xlsx(tmp_path: Path, sheets: dict[str, tuple[list, list[list]]]) -> str:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sheet_name, (header, rows) in sheets.items():
        ws = wb.create_sheet(sheet_name)
        ws.append(header)
        for row in rows:
            ws.append(row)
    path = tmp_path / "collection.xlsx"
    wb.save(path)
    return str(path)


def _import(path, records, covers_dir, metron=None, google_books=None, open_library=None):
    return import_physical_xlsx(
        path, records,
        metron=metron if metron is not None else FakeMetron(),
        google_books=google_books if google_books is not None else FakeGoogleBooks(),
        open_library=open_library if open_library is not None else FakeOpenLibrary(),
        covers_dir=covers_dir,
    )


def test_comics_upc_row_routes_to_metron(tmp_path):
    path = make_xlsx(tmp_path, {"comics": (["Name", "UPC/ISBN"], [["Absolute Batman #10", "76194138584601011"]])})
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(upc_result={"desc": "A synopsis.", "image": "https://example.com/cover.jpg", "credits": []})

    stats = _import(path, records, metron=metron, covers_dir=tmp_path / "covers")

    assert stats["comics_added"] == 1
    assert metron.upc_calls == ["76194138584601011"]
    record = records["upc-76194138584601011"]
    assert record.type == "comic"
    assert record.formats == ["print"]
    assert record.upc == "76194138584601011"
    assert record.description == "A synopsis."
    assert record.cover_path == "upc-76194138584601011/cover.jpg"
    assert record.metadata_source["cover_path"] == "metron"


def test_comics_upc_row_fills_publisher_and_year_from_store_date(tmp_path):
    path = make_xlsx(tmp_path, {"comics": (["Name", "UPC/ISBN"], [["Absolute Batman #10", "76194138584601011"]])})
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(upc_result={
        "publisher": {"name": "DC Comics"},
        "store_date": "2025-07-16",
        "cover_date": "2025-09-01",
        "credits": [],
    })

    _import(path, records, metron=metron, covers_dir=tmp_path / "covers")

    record = records["upc-76194138584601011"]
    assert record.publisher == "DC Comics"
    assert record.year == 2025  # from store_date, not cover_date


def test_comics_upc_miss_falls_back_to_exact_series_and_number(tmp_path):
    path = make_xlsx(tmp_path, {"comics": (["Name", "UPC/ISBN"], [["Absolute Batman #17", "76194138584601700"]])})
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(
        upc_result=None,
        series_number_result={"desc": "found via exact issue number", "image": "https://example.com/c.jpg", "credits": []},
    )

    stats = _import(path, records, metron=metron, covers_dir=tmp_path / "covers")

    assert stats["comics_added"] == 1
    assert metron.upc_calls == ["76194138584601700"]
    assert metron.search_calls == []
    assert metron.series_number_calls == [("Absolute Batman #17", "17")]
    record = records["upc-76194138584601700"]
    assert record.description == "found via exact issue number"
    assert record.cover_path is not None


def test_comics_isbn_shaped_code_routes_to_open_library_not_metron(tmp_path):
    """A collected edition (TPB/HC) on the Comics sheet is stocked under a
    real book ISBN, not a Diamond UPC — its code starts with 9 and must be
    routed like a manga row, not through Metron (which has no ISBN index)."""
    path = make_xlsx(tmp_path, {"comics": (["Name", "UPC/ISBN"], [["Batman: Year One TP", "9781401207526"]])})
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron()
    open_library = FakeOpenLibrary(isbn_result={
        "author": "Frank Miller",
        "description": "Year One.",
        "_image_url": "https://covers.openlibrary.org/b/id/2-L.jpg",
    })

    stats = _import(path, records, metron=metron, open_library=open_library, covers_dir=tmp_path / "covers")

    assert stats["comics_added"] == 1
    assert metron.upc_calls == []
    assert metron.search_calls == []
    record = records["isbn-9781401207526"]
    assert record.type == "comic"
    assert record.isbn == "9781401207526"
    assert record.upc is None
    assert record.author == "Frank Miller"
    assert record.cover_path == "isbn-9781401207526/cover.jpg"
    assert record.metadata_source["cover_path"] == "open_library"


def test_comics_18_digit_isbn_price_addon_is_truncated_to_13(tmp_path):
    """A print book's barcode is sometimes ISBN-13 + a 5-digit price
    add-on (18 digits total) — only the first 13 digits are a real ISBN;
    looked up whole, every source would return nothing."""
    path = make_xlsx(tmp_path, {"comics": (["Name", "UPC/ISBN"], [["Essential Hulk Vol. 1 TP", "978078510993851499"]])})
    records: dict[str, ComicRecord] = {}
    open_library = FakeOpenLibrary(isbn_result={"author": "Stan Lee"})

    stats = _import(path, records, open_library=open_library, covers_dir=tmp_path / "covers")

    assert stats["comics_added"] == 1
    assert open_library.calls == ["9780785109938"]
    record = records["isbn-9780785109938"]
    assert record.isbn == "9780785109938"


def test_manga_isbn_row_routes_to_open_library_first_google_books_fills_description(tmp_path):
    path = make_xlsx(tmp_path, {"manga": (["Name", "UPC/ISBN"], [["Attack on Titan, Vol. 29", "9781632368287"]])})
    records: dict[str, ComicRecord] = {}
    open_library = FakeOpenLibrary(isbn_result={
        "author": "Hajime Isayama",
        "_image_url": "https://covers.openlibrary.org/b/id/1-L.jpg",
    })
    google_books = FakeGoogleBooks(isbn_result={"description": "Titans.", "author": "wrong author, should be ignored"})

    stats = _import(path, records, google_books=google_books, open_library=open_library, covers_dir=tmp_path / "covers")

    assert stats["manga_added"] == 1
    assert open_library.calls == ["9781632368287"]
    assert google_books.calls == ["9781632368287"]  # still tried, to fill in description
    record = records["isbn-9781632368287"]
    assert record.author == "Hajime Isayama"
    assert record.description == "Titans."
    assert record.issue_number == "29"
    assert record.cover_path == "isbn-9781632368287/cover.jpg"
    assert record.metadata_source["cover_path"] == "open_library"


def test_manga_isbn_falls_back_to_google_books_cover_when_open_library_has_none(tmp_path):
    path = make_xlsx(tmp_path, {"manga": (["Name", "UPC/ISBN"], [["Attack on Titan, Vol. 29", "9781632368287"]])})
    records: dict[str, ComicRecord] = {}
    open_library = FakeOpenLibrary(isbn_result={"author": "Hajime Isayama"})  # no _image_url
    google_books = FakeGoogleBooks(isbn_result={"description": "Titans.", "_image_url": "https://example.com/gb.jpg"})

    stats = _import(path, records, google_books=google_books, open_library=open_library, covers_dir=tmp_path / "covers")

    assert stats["manga_added"] == 1
    record = records["isbn-9781632368287"]
    assert record.cover_path == "isbn-9781632368287/cover.jpg"
    assert record.metadata_source["cover_path"] == "google_books"


def test_comics_upc_merges_into_existing_digital_record(tmp_path):
    records: dict[str, ComicRecord] = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="10", formats=["digital"], cover_path="d1/cover.jpg",
        )
    }
    path = make_xlsx(tmp_path, {"comics": (["Name", "UPC/ISBN"], [["Absolute Batman #10", "76194138584601011"]])})
    metron = FakeMetron(upc_result={"series": {"name": "Absolute Batman"}, "number": "10", "credits": []})

    stats = _import(path, records, metron=metron, covers_dir=tmp_path / "covers")

    assert stats["comics_merged"] == 1
    assert stats["comics_added"] == 0
    assert records["d1"].formats == ["digital", "print"]
    assert records["d1"].upc == "76194138584601011"
    assert records["d1"].cover_path == "d1/cover.jpg"  # untouched, reused
    assert "upc-76194138584601011" not in records


def test_corrupted_code_row_is_skipped(tmp_path):
    path = make_xlsx(tmp_path, {"comics": (["Name", "UPC/ISBN"], [["Absolute Batman #9", 7.61941385846009e16]])})
    records: dict[str, ComicRecord] = {}

    stats = _import(path, records, covers_dir=tmp_path / "covers")

    assert stats["comics_added"] == 0
    assert stats["skipped_corrupted_code"] == 1
    assert records == {}


def test_duplicate_upc_is_skipped_without_network_call(tmp_path):
    records: dict[str, ComicRecord] = {
        "upc-76194138584601011": ComicRecord(
            id="upc-76194138584601011", title="Absolute Batman #10", type="comic",
            upc="76194138584601011", formats=["print"],
        )
    }
    path = make_xlsx(tmp_path, {"comics": (["Name", "UPC/ISBN"], [["Absolute Batman #10", "76194138584601011"]])})
    metron = FakeMetron()

    stats = _import(path, records, metron=metron, covers_dir=tmp_path / "covers")

    assert stats["skipped_duplicate"] == 1
    assert metron.upc_calls == []


def test_both_sheets_are_imported_in_one_pass(tmp_path):
    path = make_xlsx(tmp_path, {
        "comics": (["Name", "UPC/ISBN"], [["Absolute Batman #10", "76194138584601011"]]),
        "manga": (["Name", "UPC/ISBN"], [["Attack on Titan, Vol. 29", "9781632368287"]]),
    })
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(upc_result={"desc": "x", "credits": []})

    stats = _import(path, records, metron=metron, covers_dir=tmp_path / "covers")

    assert stats["comics_added"] == 1
    assert stats["manga_added"] == 1
    assert records["upc-76194138584601011"].type == "comic"
    assert records["isbn-9781632368287"].type == "manga"
