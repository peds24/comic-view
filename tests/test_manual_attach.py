from pathlib import Path

import pytest

from library.manual_attach import (
    LinkAttachError,
    attach_comic_geeks_issue,
    attach_cover_bytes,
    attach_from_link,
    set_formats,
    set_title,
    set_year,
)
from library.models import ComicRecord


class FakeCoverResponse:
    content = b"fake-cover-bytes"

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _fake_cover_download(monkeypatch):
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())


def _record(**overrides):
    defaults = dict(id="upc-1", title="Absolute Batman #16 2nd Printing", type="comic", formats=["print"])
    defaults.update(overrides)
    return ComicRecord(**defaults)


# --- attach_cover_bytes ---


def test_attach_cover_bytes(tmp_path: Path):
    record = _record()
    attach_cover_bytes(record, b"cover-bytes", ".jpg", tmp_path)
    assert record.cover_path == "upc-1/cover.jpg"
    assert record.metadata_source["cover_path"] == "manual"
    assert (tmp_path / "upc-1" / "cover.jpg").read_bytes() == b"cover-bytes"


# --- attach_comic_geeks_issue ---


def test_attach_comic_geeks_issue_overwrites_all_but_title(tmp_path: Path, monkeypatch):
    record = _record(
        title="Absolute Batman #16 2nd Printing",
        series="wrong series", issue_number="wrong", publisher="wrong pub",
        year=1999, description="wrong desc", author="wrong author",
    )
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {
        "series": "Absolute Batman", "issue_number": "16", "publisher": "DC Comics", "year": 2026,
        "description": "A synopsis.", "author": "Scott Snyder, Nick Dragotta", "upc": "76194138584601611",
        "_image_url": "https://example.com/cover.jpg",
    })

    attach_comic_geeks_issue(record, "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", tmp_path)

    assert record.title == "Absolute Batman #16 2nd Printing"  # untouched
    assert record.series == "Absolute Batman"
    assert record.issue_number == "16"
    assert record.publisher == "DC Comics"
    assert record.year == 2026
    assert record.description == "A synopsis."
    assert record.author == "Scott Snyder, Nick Dragotta"
    assert record.upc == "76194138584601611"
    assert record.metadata_source["series"] == "comic_geeks"
    assert record.metadata_source["upc"] == "comic_geeks"
    assert record.cover_path == "upc-1/cover.jpg"
    assert record.metadata_source["cover_path"] == "comic_geeks"


def test_attach_comic_geeks_issue_raises_when_page_unreadable(tmp_path: Path, monkeypatch):
    record = _record()
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {})
    with pytest.raises(LinkAttachError):
        attach_comic_geeks_issue(record, "https://leagueofcomicgeeks.com/comic/1/x", tmp_path)


# --- attach_from_link ---


def test_attach_from_link_routes_comic_geeks_url(tmp_path: Path, monkeypatch):
    record = _record()
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {"publisher": "DC Comics"})
    attach_from_link(record, "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", covers_dir=tmp_path)
    assert record.publisher == "DC Comics"


def test_attach_from_link_rejects_non_comic_geeks_url(tmp_path: Path):
    record = _record()
    with pytest.raises(LinkAttachError):
        attach_from_link(record, "https://metron.cloud/issue/absolute-batman-2024-16/", covers_dir=tmp_path)


# --- set_title ---


def test_set_title_overwrites_title_and_marks_source_manual():
    record = _record()
    set_title(record, "Absolute Batman #16")
    assert record.title == "Absolute Batman #16"
    assert record.metadata_source["title"] == "manual"


# --- set_year ---


def test_set_year_overwrites_year_and_marks_source_manual():
    record = _record()
    set_year(record, 2016)
    assert record.year == 2016
    assert record.metadata_source["year"] == "manual"


def test_set_year_none_clears_year_and_its_source():
    record = _record(year=2016, metadata_source={"year": "filename"})
    set_year(record, None)
    assert record.year is None
    assert "year" not in record.metadata_source


# --- set_formats ---


def test_set_formats_overwrites_formats():
    record = _record(formats=["digital"])
    set_formats(record, ["digital", "print"])
    assert record.formats == ["digital", "print"]
