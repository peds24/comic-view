from library.matching import (
    extract_issue,
    extract_manga_issue,
    find_digital_match,
    find_matching_record,
    is_matchable,
    normalize_issue,
    normalize_series,
    strip_issue_suffix,
    strip_manga_volume_suffix,
)
from library.models import ComicRecord


def test_normalize_series_strips_year_range_suffix():
    assert normalize_series("Absolute Batman (2024 - Present)") == "Absolute Batman"
    assert normalize_series("Swamp Thing 1989") == "Swamp Thing 1989"


def test_normalize_series_strips_volume_suffix():
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


def test_extract_manga_issue_vol_style():
    assert extract_manga_issue("Hunter x Hunter, Vol. 6") == "6"


def test_extract_manga_issue_trailing_number():
    assert extract_manga_issue("Attack on Titan 29") == "29"


def test_extract_manga_issue_none_when_no_number():
    assert extract_manga_issue("Monster") is None


def test_strip_manga_volume_suffix_vol_style():
    assert strip_manga_volume_suffix("Hunter x Hunter, Vol. 6") == "Hunter x Hunter"


def test_strip_manga_volume_suffix_trailing_number():
    assert strip_manga_volume_suffix("Attack on Titan 29") == "Attack on Titan"


def test_strip_manga_volume_suffix_no_number_returns_title_unchanged():
    assert strip_manga_volume_suffix("Monster") == "Monster"


def test_is_matchable_requires_issue_number():
    assert is_matchable("Absolute Batman #9", "9") is True
    assert is_matchable("Kingdom Come: 30th Anniversary Deluxe Edition HC", None) is False


def test_is_matchable_excludes_collected_edition_keywords():
    assert is_matchable("Absolute Batman 2025 Annual #1", "1") is False
    assert is_matchable("Absolute Batman #16 2nd Printing", "16") is False
    assert is_matchable("Absolute Batman Vol. 1: The Zoo HC", None) is False


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


def test_find_matching_record_matches_regardless_of_format():
    records = {
        "p1": ComicRecord(
            id="p1", title="Absolute Batman #9", type="comic", series="Absolute Batman",
            issue_number="9", formats=["print"],
        )
    }
    match = find_matching_record(records, "Absolute Batman", "9")
    assert match is not None
    assert match.id == "p1"


def test_find_matching_record_normalizes_issue_numbers():
    records = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="021", formats=["digital"],
        )
    }
    assert find_matching_record(records, "Absolute Batman", "21").id == "d1"


def test_find_matching_record_returns_none_when_no_match():
    assert find_matching_record({}, "Absolute Batman", "9") is None


def test_strip_issue_suffix_removes_hash_number():
    assert strip_issue_suffix("Batman #14") == "Batman"


def test_strip_issue_suffix_returns_title_unchanged_when_no_suffix():
    assert strip_issue_suffix("Billy Bat Vol. 2 TP") == "Billy Bat Vol. 2 TP"
