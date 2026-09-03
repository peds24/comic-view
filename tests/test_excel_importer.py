from library.excel_importer import (
    compute_physical_id,
    extract_issue,
    find_digital_match,
    import_physical,
    is_matchable,
    normalize_issue,
    normalize_series,
    parse_row,
)
from library.models import ComicRecord


def test_normalize_series_strips_year_range_suffix():
    assert normalize_series("Absolute Batman (2024 - Present)") == "Absolute Batman"
    assert normalize_series("Swamp Thing 1989") == "Swamp Thing 1989"


def test_normalize_series_strips_volume_suffix():
    # Real bug found while investigating why Metron cover lookups were
    # missing for "Batman" single issues: the series name still carried a
    # "(Vol. 4)" qualifier, polluting the search query.
    assert normalize_series("Batman (Vol. 4)") == "Batman"
    assert normalize_series("The Brave and the Bold (Vol. 1)") == "The Brave and the Bold"


def test_normalize_series_strips_bare_year_suffix():
    assert normalize_series("Swamp Thing 1989 (2026)") == "Swamp Thing 1989"


def test_normalize_series_strips_edition_note_suffix():
    assert normalize_series("Watchmen (New Edition)") == "Watchmen"
    assert normalize_series("Uzumaki (3-in-1, Deluxe Edition)") == "Uzumaki"


def test_extract_issue():
    assert extract_issue("Absolute Batman #9") == "9"
    assert extract_issue("Absolute Batman 2025 Annual #1") == "1"
    assert extract_issue("Kingdom Come: 30th Anniversary Deluxe Edition HC") is None


def test_normalize_issue_strips_leading_zeros():
    assert normalize_issue("021") == "21"
    assert normalize_issue("9") == "9"
    assert normalize_issue("01") == "1"


def test_is_matchable_requires_issue_number():
    assert is_matchable("Absolute Batman #9", "9") is True
    assert is_matchable("Kingdom Come: 30th Anniversary Deluxe Edition HC", None) is False


def test_is_matchable_excludes_collected_edition_keywords():
    assert is_matchable("Absolute Batman 2025 Annual #1", "1") is False
    assert is_matchable("Absolute Batman #16 2nd Printing", "16") is False
    assert is_matchable("Absolute Batman Vol. 1: The Zoo HC", None) is False


def test_parse_row_skips_not_in_collection():
    row = {
        "Full Title": "Absolute Batman #1",
        "Series Name": "Absolute Batman (2024 - Present)",
        "Publisher Name": "DC Comics",
        "Release Date": "2025-01-01",
        "Marked Read": 1,
        "In Collection": 0,
    }
    assert parse_row(row) is None


def test_parse_row_extracts_expected_fields():
    row = {
        "Full Title": "Absolute Batman #9",
        "Series Name": "Absolute Batman (2024 - Present)",
        "Publisher Name": "DC Comics",
        "Release Date": "2025-06-11",
        "Marked Read": 1,
        "In Collection": 1,
    }
    parsed = parse_row(row)
    assert parsed["title"] == "Absolute Batman #9"
    assert parsed["series"] == "Absolute Batman"
    assert parsed["issue_number"] == "9"
    assert parsed["publisher"] == "DC Comics"
    assert parsed["year"] == 2025
    assert parsed["status"] == "read"
    assert parsed["matchable"] is True


def test_parse_row_unread_status():
    row = {
        "Full Title": "Absolute Batman #22",
        "Series Name": "Absolute Batman (2024 - Present)",
        "Publisher Name": "DC Comics",
        "Release Date": "2026-05-01",
        "Marked Read": 0,
        "In Collection": 1,
    }
    assert parse_row(row)["status"] == "unread"


def test_compute_physical_id_is_stable_and_distinct_from_digital_shape():
    id1 = compute_physical_id("Absolute Batman", "Absolute Batman #9")
    id2 = compute_physical_id("Absolute Batman", "Absolute Batman #9")
    assert id1 == id2
    assert id1.startswith("xlsx-")


def test_find_digital_match_normalizes_issue_numbers():
    records = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="021", formats=["digital"],
        )
    }
    match = find_digital_match(records, "Absolute Batman", "21")
    assert match is not None
    assert match.id == "d1"


def test_find_digital_match_ignores_physical_only_records():
    records = {
        "p1": ComicRecord(
            id="p1", title="Absolute Batman #9", type="comic", series="Absolute Batman",
            issue_number="9", formats=["print"],
        )
    }
    assert find_digital_match(records, "Absolute Batman", "9") is None


def test_import_physical_merges_matching_digital_record():
    records = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="09", formats=["digital"],
            cover_path="d1/cover.jpg", preview_pages=["d1/page-01.jpg"],
        )
    }
    rows = [{
        "Full Title": "Absolute Batman #9",
        "Series Name": "Absolute Batman (2024 - Present)",
        "Publisher Name": "DC Comics",
        "Release Date": "2025-06-11",
        "Marked Read": 1,
        "In Collection": 1,
    }]
    merged, new, skipped = import_physical(records, rows)
    assert (merged, new, skipped) == (1, 0, 0)
    assert records["d1"].formats == ["digital", "print"]
    assert records["d1"].cover_path == "d1/cover.jpg"  # untouched, reused


def test_import_physical_creates_physical_only_record_when_no_match():
    records: dict = {}
    rows = [{
        "Full Title": "Kingdom Come: 30th Anniversary Deluxe Edition HC",
        "Series Name": "Kingdom Come",
        "Publisher Name": "DC Comics",
        "Release Date": "2026-01-01",
        "Marked Read": 0,
        "In Collection": 1,
    }]
    merged, new, skipped = import_physical(records, rows)
    assert (merged, new, skipped) == (0, 1, 0)
    (record,) = records.values()
    assert record.formats == ["print"]
    assert record.cover_path is None
    assert record.preview_pages == []


def test_import_physical_skips_not_in_collection_rows():
    records: dict = {}
    rows = [{
        "Full Title": "Batman: The Dark Knight Returns Deluxe Edition HC",
        "Series Name": "Batman",
        "Publisher Name": "DC Comics",
        "Release Date": "2020-01-01",
        "Marked Read": 0,
        "In Collection": 0,
    }]
    merged, new, skipped = import_physical(records, rows)
    assert (merged, new, skipped) == (0, 0, 1)
    assert records == {}


def test_import_physical_is_idempotent():
    records = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="09", formats=["digital"],
        )
    }
    rows = [{
        "Full Title": "Absolute Batman #9",
        "Series Name": "Absolute Batman (2024 - Present)",
        "Publisher Name": "DC Comics",
        "Release Date": "2025-06-11",
        "Marked Read": 1,
        "In Collection": 1,
    }]
    import_physical(records, rows)
    merged, new, skipped = import_physical(records, rows)
    assert (merged, new, skipped) == (0, 0, 0)
    assert records["d1"].formats == ["digital", "print"]
