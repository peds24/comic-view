from pathlib import Path

from library.isbn_importer import (
    import_isbn_csv,
    is_matchable,
    is_valid_isbn13,
    parse_title,
)
from library.models import ComicRecord


def test_is_valid_isbn13():
    assert is_valid_isbn13("9781632368287") is True
    assert is_valid_isbn13("9781632369024") is True
    assert is_valid_isbn13("2241421599614") is False  # real mis-scanned price barcode
    assert is_valid_isbn13("97816323682") is False  # too short


# parse_title cases below use real titles returned by Google Books for ISBNs
# in the actual export, inspected during design.


def test_parse_title_bare_trailing_number():
    assert parse_title("Attack on Titan 29") == ("Attack on Titan", "29")


def test_parse_title_vol_dot_pattern():
    assert parse_title("Hunter x Hunter, Vol. 36") == ("Hunter x Hunter", "36")


def test_parse_title_volume_spelled_out():
    assert parse_title("Akira Volume 1") == ("Akira", "1")


def test_parse_title_colon_subtitle_with_trailing_number():
    assert parse_title("Mobile Suit Gundam: THE ORIGIN 1") == ("Mobile Suit Gundam: THE ORIGIN", "1")


def test_parse_title_no_volume():
    assert parse_title("No Longer Human") == ("No Longer Human", None)
    assert parse_title("Naruto: Awakening") == ("Naruto: Awakening", None)


def test_parse_title_strips_trailing_parenthetical_from_series():
    series, vol = parse_title("Vagabond (VIZBIG Edition), Vol. 2")
    assert series == "Vagabond"
    assert vol == "2"


def test_is_matchable_requires_volume():
    assert is_matchable("Monster, Vol. 9", "9") is True
    assert is_matchable("Monster", None) is False


def test_is_matchable_excludes_variant_editions():
    assert is_matchable("Monster: The Perfect Edition, Vol. 8", "8") is False
    assert is_matchable("One Piece (Omnibus Edition), Vol. 1", "1") is False
    assert is_matchable("Vagabond (VIZBIG Edition), Vol. 2", "2") is False


class FakeGoogleBooksSource:
    name = "google_books"

    def __init__(self, isbn_results: dict, cover_fallback_url: str | None = None):
        self._isbn_results = isbn_results
        self._cover_fallback_url = cover_fallback_url

    def lookup_isbn(self, isbn: str) -> dict:
        return self._isbn_results.get(isbn, {})

    def cover_image_url(self, title: str, year=None) -> str | None:
        return self._cover_fallback_url


class FakeResponse:
    def __init__(self, content=b"fake-bytes"):
        self.content = content

    def raise_for_status(self):
        pass


def test_import_creates_new_physical_manga_record(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.isbn_importer.requests.get", lambda *a, **k: FakeResponse())
    source = FakeGoogleBooksSource({
        "9781632368287": {
            "title": "Attack on Titan 29", "author": "Hajime Isayama",
            "publisher": "National Geographic Books", "year": 2019,
            "_image_url": "https://example.com/cover.jpg",
        }
    })
    records: dict = {}
    rows = [{"text": "9781632368287"}]

    merged, new, skipped_invalid, skipped_no_result = import_isbn_csv(records, rows, source, tmp_path)

    assert (merged, new, skipped_invalid, skipped_no_result) == (0, 1, 0, 0)
    record = records["isbn-9781632368287"]
    assert record.title == "Attack on Titan 29"
    assert record.series == "Attack on Titan"
    assert record.issue_number == "29"
    assert record.type == "manga"
    assert record.formats == ["physical"]
    assert record.status == "unread"
    assert record.cover_path == "isbn-9781632368287/cover.jpg"
    assert record.preview_pages == []


def test_import_merges_into_matching_digital_record(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.isbn_importer.requests.get", lambda *a, **k: FakeResponse())
    records = {
        "d1": ComicRecord(
            id="d1", title="Monster", type="manga", series="Monster",
            issue_number="09", formats=["digital"],
            cover_path="d1/cover.jpg",
        )
    }
    source = FakeGoogleBooksSource({
        "9781421569147": {"title": "Monster, Vol. 9", "_image_url": "https://example.com/c.jpg"}
    })
    merged, new, skipped_invalid, skipped_no_result = import_isbn_csv(
        records, [{"text": "9781421569147"}], source, tmp_path
    )
    assert (merged, new, skipped_invalid, skipped_no_result) == (1, 0, 0, 0)
    assert records["d1"].formats == ["digital", "physical"]
    assert records["d1"].cover_path == "d1/cover.jpg"  # untouched


def test_import_skips_invalid_barcode():
    records: dict = {}
    source = FakeGoogleBooksSource({})
    merged, new, skipped_invalid, skipped_no_result = import_isbn_csv(
        records, [{"text": "2241421599614"}], source, Path("/tmp")
    )
    assert (merged, new, skipped_invalid, skipped_no_result) == (0, 0, 1, 0)


def test_import_skips_isbn_with_no_lookup_result():
    records: dict = {}
    source = FakeGoogleBooksSource({})  # empty -> no result for any isbn
    merged, new, skipped_invalid, skipped_no_result = import_isbn_csv(
        records, [{"text": "9789999999999"}], source, Path("/tmp")
    )
    assert (merged, new, skipped_invalid, skipped_no_result) == (0, 0, 0, 1)


def test_import_falls_back_to_title_search_when_isbn_edition_has_no_cover(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.isbn_importer.requests.get", lambda *a, **k: FakeResponse())
    source = FakeGoogleBooksSource(
        {"9781646510313": {"title": "Attack on Titan 32"}},  # no _image_url
        cover_fallback_url="https://example.com/fallback.jpg",
    )
    records: dict = {}
    merged, new, skipped_invalid, skipped_no_result = import_isbn_csv(
        records, [{"text": "9781646510313"}], source, tmp_path
    )
    assert new == 1
    record = records["isbn-9781646510313"]
    assert record.cover_path == "isbn-9781646510313/cover.jpg"


def test_import_is_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.isbn_importer.requests.get", lambda *a, **k: FakeResponse())
    source = FakeGoogleBooksSource({
        "9781632368287": {"title": "Attack on Titan 29", "_image_url": "https://example.com/c.jpg"}
    })
    records: dict = {}
    rows = [{"text": "9781632368287"}]
    import_isbn_csv(records, rows, source, tmp_path)
    merged, new, skipped_invalid, skipped_no_result = import_isbn_csv(records, rows, source, tmp_path)
    assert (merged, new, skipped_invalid, skipped_no_result) == (0, 0, 0, 0)
    assert len(records) == 1
