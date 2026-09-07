from library.models import ComicRecord
from library.sheets_sync import _HEADER, _comic_to_row


def _record(**overrides) -> ComicRecord:
    defaults = dict(
        id="cgeeks-1",
        title="Absolute Batman #16",
        type="comic",
        series="Absolute Batman",
        issue_number="16",
        author="Scott Snyder",
        year=2026,
        publisher="DC Comics",
        status="unread",
        formats=["digital"],
        added_date="2026-09-07",
    )
    defaults.update(overrides)
    return ComicRecord(**defaults)


def test_header_matches_row_length():
    assert len(_HEADER) == len(_comic_to_row(_record()))


def test_comic_to_row_uses_series_and_issue_for_title():
    row = _comic_to_row(_record())
    assert row == [
        "Absolute Batman #16", "Absolute Batman", "16", "Scott Snyder",
        "2026", "DC Comics", "unread", "digital", "2026-09-07",
    ]


def test_comic_to_row_falls_back_to_title_without_series_or_issue():
    record = _record(title="Some One-Shot", series=None, issue_number=None)
    row = _comic_to_row(record)
    assert row[0] == "Some One-Shot"
    assert row[1] == ""
    assert row[2] == ""


def test_comic_to_row_blanks_missing_optional_fields():
    record = _record(author=None, year=None, publisher=None)
    row = _comic_to_row(record)
    assert row[3] == ""  # author
    assert row[4] == ""  # year
    assert row[5] == ""  # publisher


def test_comic_to_row_joins_multiple_formats():
    record = _record(formats=["digital", "print"])
    row = _comic_to_row(record)
    assert row[7] == "digital, print"
