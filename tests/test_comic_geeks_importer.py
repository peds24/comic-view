from pathlib import Path

import openpyxl
import pytest

from library.comic_geeks_importer import classify_code, extract_manga_issue, import_comic_geeks_xlsx
from library.models import ComicRecord


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
        "library.comic_geeks_importer.requests.get",
        lambda *a, **k: FakeCoverResponse(),
    )


def make_xlsx(tmp_path: Path, header: list, rows: list[list]) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Comics"
    ws.append(header)
    for row in rows:
        ws.append(row)
    path = tmp_path / "export.xlsx"
    wb.save(path)
    return str(path)


COMIC_HEADER = [
    "Publisher Name", "Series Name", "Full Title", "Release Date",
    "In Collection", "In Wish List", "Marked Read", "My Rating",
    "Media Format", "UPC / ISBN",
]
MANGA_HEADER = [
    "Publisher Name", "Series Name", "Full Title", "Release Date",
    "In Collection", "In Wish List", "Marked Read", "My Rating",
    "Media Format", "ISBN",
]


def test_classify_code_isbn():
    assert classify_code("9781632368287") == ("isbn", "9781632368287")


def test_classify_code_upc_string():
    assert classify_code("76194138584601011") == ("upc", "76194138584601011")


def test_classify_code_corrupted_float():
    assert classify_code(7.6194138584601104e16) == ("corrupted", None)


def test_classify_code_isbn_with_price_addon():
    """An 18-digit EAN — ISBN-13 + 5-digit price add-on, a common print-book
    barcode convention — is still an ISBN lookup, just truncated to 13."""
    assert classify_code("978078510993851000") == ("isbn", "9780785109938")


def test_classify_code_clean_int_isbn():
    assert classify_code(9781799505242) == ("isbn", "9781799505242")


def test_classify_code_none():
    assert classify_code(None) == ("none", None)
    assert classify_code("") == ("none", None)


def test_extract_manga_issue_vol_style():
    assert extract_manga_issue("Hunter x Hunter, Vol. 6") == "6"


def test_extract_manga_issue_trailing_number():
    assert extract_manga_issue("Attack on Titan 29") == "29"


def test_extract_manga_issue_none_when_no_number():
    assert extract_manga_issue("Monster") is None


def test_upc_row_routes_to_metron(tmp_path):
    path = make_xlsx(
        tmp_path, COMIC_HEADER,
        [["DC Comics", "Absolute Batman", "Absolute Batman #10", "2025-07-16", 1, 0, 1, None, "Print", "76194138584601011"]],
    )
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(upc_result={"desc": "A synopsis.", "image": "https://example.com/cover.jpg", "credits": []})
    google_books = FakeGoogleBooks()
    open_library = FakeOpenLibrary()

    stats = import_comic_geeks_xlsx(
        path, "comic", records,
        metron=metron, google_books=google_books, open_library=open_library, covers_dir=tmp_path / "covers",
    )

    assert stats["new"] == 1
    assert metron.upc_calls == ["76194138584601011"]
    assert google_books.calls == []
    record = records["upc-76194138584601011"]
    assert record.type == "comic"
    assert record.formats == ["print"]
    assert record.isbn == "76194138584601011"
    assert record.description == "A synopsis."
    assert record.cover_path == "upc-76194138584601011/cover.jpg"
    assert record.metadata_source["cover_path"] == "metron"


def test_upc_row_falls_back_to_exact_series_and_number_when_metron_upc_has_no_match(tmp_path):
    path = make_xlsx(
        tmp_path, COMIC_HEADER,
        [["DC Comics", "Absolute Batman", "Absolute Batman #17", "2025-11-01", 1, 0, 0, None, "Print", "76194138584601700"]],
    )
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(
        upc_result=None,  # Metron's UPC index has no entry for this one
        series_number_result={"desc": "found via exact issue number", "image": "https://example.com/title-cover.jpg", "credits": []},
    )

    stats = import_comic_geeks_xlsx(
        path, "comic", records,
        metron=metron, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path / "covers",
    )

    assert stats["new"] == 1
    assert metron.upc_calls == ["76194138584601700"]
    # Never falls through to fuzzy title+year search — that's what caused
    # different issues of the same series to get the same wrong cover.
    assert metron.search_calls == []
    assert metron.series_number_calls == [("Absolute Batman", "17")]
    record = records["upc-76194138584601700"]
    assert record.description == "found via exact issue number"
    assert record.cover_path is not None


def test_isbn_row_routes_to_open_library_first_google_books_fills_description(tmp_path):
    """Open Library first, Google Books as fallback — the routing proven in
    the longbox app. Open Library has no description field, so Google Books
    still runs to fill that in even though Open Library already supplied
    author/cover."""
    path = make_xlsx(
        tmp_path, MANGA_HEADER,
        [["Kodansha Comics", "Attack on Titan", "Attack on Titan 29", "2019-12-03", 1, 0, 0, None, "Print", "9781632368287"]],
    )
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron()
    open_library = FakeOpenLibrary(isbn_result={
        "author": "Hajime Isayama",
        "_image_url": "https://covers.openlibrary.org/b/id/1-L.jpg",
    })
    google_books = FakeGoogleBooks(isbn_result={"description": "Titans.", "author": "wrong author, should be ignored"})

    stats = import_comic_geeks_xlsx(
        path, "manga", records,
        metron=metron, google_books=google_books, open_library=open_library, covers_dir=tmp_path / "covers",
    )

    assert stats["new"] == 1
    assert open_library.calls == ["9781632368287"]
    assert google_books.calls == ["9781632368287"]  # still tried, to fill in description
    record = records["isbn-9781632368287"]
    assert record.author == "Hajime Isayama"  # Open Library's value wins, Google Books' is ignored
    assert record.description == "Titans."
    assert record.issue_number == "29"
    assert record.cover_path == "isbn-9781632368287/cover.jpg"
    assert record.metadata_source["cover_path"] == "open_library"


def test_isbn_row_falls_back_to_google_books_cover_when_open_library_has_none(tmp_path):
    path = make_xlsx(
        tmp_path, MANGA_HEADER,
        [["Kodansha Comics", "Attack on Titan", "Attack on Titan 29", "2019-12-03", 1, 0, 0, None, "Print", "9781632368287"]],
    )
    records: dict[str, ComicRecord] = {}
    open_library = FakeOpenLibrary(isbn_result={"author": "Hajime Isayama"})  # no _image_url
    google_books = FakeGoogleBooks(isbn_result={"description": "Titans.", "_image_url": "https://example.com/gb.jpg"})

    stats = import_comic_geeks_xlsx(
        path, "manga", records,
        metron=FakeMetron(), google_books=google_books, open_library=open_library, covers_dir=tmp_path / "covers",
    )

    assert stats["new"] == 1
    record = records["isbn-9781632368287"]
    assert record.cover_path == "isbn-9781632368287/cover.jpg"
    assert record.metadata_source["cover_path"] == "google_books"


def test_corrupted_code_row_is_skipped(tmp_path):
    path = make_xlsx(
        tmp_path, COMIC_HEADER,
        [["DC Comics", "Absolute Batman", "Absolute Batman #9", "2025-06-11", 1, 0, 1, None, "Print", 7.61941385846009e16]],
    )
    records: dict[str, ComicRecord] = {}
    stats = import_comic_geeks_xlsx(
        path, "comic", records,
        metron=FakeMetron(), google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path / "covers",
    )
    assert stats["new"] == 0
    assert stats["skipped_corrupted_code"] == 1
    assert records == {}


def test_blank_code_row_with_issue_number_uses_exact_series_and_number(tmp_path):
    path = make_xlsx(
        tmp_path, COMIC_HEADER,
        [["DC Comics", "Some Series", "Some Series #1", "2020-01-01", 1, 0, 0, None, "Print", None]],
    )
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(series_number_result={"desc": "desc", "image": "https://example.com/c.jpg", "credits": []})

    stats = import_comic_geeks_xlsx(
        path, "comic", records,
        metron=metron, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path / "covers",
    )

    assert stats["new"] == 1
    assert metron.series_number_calls == [("Some Series", "1")]
    assert metron.search_calls == []
    record = next(iter(records.values()))
    assert record.description == "desc"
    assert record.cover_path is not None


def test_blank_code_row_without_issue_number_falls_back_to_fuzzy_title_search(tmp_path):
    """Only a TPB/collection without a parseable issue number reaches the
    old fuzzy title+year search — never a second attempt after an exact
    series+number match already failed."""
    path = make_xlsx(
        tmp_path, COMIC_HEADER,
        [["DC Comics", "Some Series", "Some Series Omnibus", "2020-01-01", 1, 0, 0, None, "Print", None]],
    )
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(search_result={"publisher": "DC Comics", "description": "desc"}, cover_url="https://example.com/c.jpg")

    stats = import_comic_geeks_xlsx(
        path, "comic", records,
        metron=metron, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path / "covers",
    )

    assert stats["new"] == 1
    assert metron.series_number_calls == []
    assert metron.search_calls == [("Some Series", 2020)]
    record = next(iter(records.values()))
    assert record.description == "desc"
    assert record.cover_path is not None


def test_not_in_collection_row_is_skipped(tmp_path):
    path = make_xlsx(
        tmp_path, COMIC_HEADER,
        [["DC Comics", "X", "X #1", "2020-01-01", 0, 0, 0, None, "Print", None]],
    )
    records: dict[str, ComicRecord] = {}
    stats = import_comic_geeks_xlsx(
        path, "comic", records,
        metron=FakeMetron(), google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path / "covers",
    )
    assert stats["skipped_not_in_collection"] == 1
    assert records == {}
