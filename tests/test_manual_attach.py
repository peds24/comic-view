from pathlib import Path

import pytest

from library.manual_attach import (
    LinkAttachError,
    _parse_metron_url,
    attach_comic_geeks_issue,
    attach_cover_bytes,
    attach_from_link,
    attach_metron_issue,
)
from library.models import ComicRecord


class FakeMetron:
    def __init__(self, issue=None):
        self.issue = issue
        self.by_id_calls = []
        self.series_number_calls = []

    def get_issue_by_id(self, issue_id):
        self.by_id_calls.append(issue_id)
        return self.issue

    def find_issue_by_series_and_number(self, series, number, year=None):
        self.series_number_calls.append((series, number, year))
        return self.issue


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


# --- _parse_metron_url ---


def test_parse_metron_url_slug_with_year():
    assert _parse_metron_url("https://metron.cloud/issue/absolute-batman-2024-16/") == (
        "absolute batman", "16", 2024,
    )


def test_parse_metron_url_slug_without_trailing_slash():
    assert _parse_metron_url("https://metron.cloud/issue/absolute-batman-2024-16") == (
        "absolute batman", "16", 2024,
    )


def test_parse_metron_url_numeric_id():
    assert _parse_metron_url("https://metron.cloud/issue/158565/") == 158565


def test_parse_metron_url_bare_numeric_id():
    assert _parse_metron_url("158565") == 158565


def test_parse_metron_url_slug_without_year():
    assert _parse_metron_url("https://metron.cloud/issue/monster-1") == ("monster", "1", None)


def test_parse_metron_url_unparseable_raises():
    with pytest.raises(LinkAttachError):
        _parse_metron_url("https://metron.cloud/issue/")


# --- attach_cover_bytes ---


def test_attach_cover_bytes(tmp_path: Path):
    record = _record()
    attach_cover_bytes(record, b"cover-bytes", ".jpg", tmp_path)
    assert record.cover_path == "upc-1/cover.jpg"
    assert record.metadata_source["cover_path"] == "manual"
    assert (tmp_path / "upc-1" / "cover.jpg").read_bytes() == b"cover-bytes"


# --- attach_metron_issue ---


def _issue(**overrides):
    defaults = dict(
        series={"name": "Absolute Batman"},
        number="16",
        publisher={"name": "DC Comics"},
        store_date="2026-01-28",
        desc="A synopsis.",
        credits=[{"creator": "Scott Snyder", "role": [{"name": "Writer"}]}],
        image="https://example.com/cover.jpg",
    )
    defaults.update(overrides)
    return defaults


def test_attach_metron_issue_by_numeric_id_overwrites_all_but_title(tmp_path: Path):
    record = _record(
        title="Absolute Batman #16 2nd Printing",
        series="wrong series", issue_number="wrong", publisher="wrong pub",
        year=1999, description="wrong desc", author="wrong author",
    )
    metron = FakeMetron(issue=_issue())

    attach_metron_issue(record, metron, "https://metron.cloud/issue/158565/", tmp_path)

    assert metron.by_id_calls == [158565]
    assert record.title == "Absolute Batman #16 2nd Printing"  # untouched
    assert record.series == "Absolute Batman"
    assert record.issue_number == "16"
    assert record.publisher == "DC Comics"
    assert record.year == 2026
    assert record.description == "A synopsis."
    assert record.author == "Scott Snyder"
    assert record.metadata_source["series"] == "metron"
    assert record.metadata_source["year"] == "metron"


def test_attach_metron_issue_by_slug_resolves_via_series_and_number(tmp_path: Path):
    record = _record()
    metron = FakeMetron(issue=_issue())

    attach_metron_issue(record, metron, "https://metron.cloud/issue/absolute-batman-2024-16/", tmp_path)

    assert metron.series_number_calls == [("absolute batman", "16", 2024)]
    assert record.cover_path == "upc-1/cover.jpg"
    assert record.metadata_source["cover_path"] == "metron"


def test_attach_metron_issue_raises_when_metron_has_no_match(tmp_path: Path):
    record = _record()
    metron = FakeMetron(issue=None)
    with pytest.raises(LinkAttachError):
        attach_metron_issue(record, metron, "https://metron.cloud/issue/158565/", tmp_path)


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


# --- attach_from_link (auto-detect) ---


def test_attach_from_link_routes_comic_geeks_url_without_metron(tmp_path: Path, monkeypatch):
    record = _record()
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {"publisher": "DC Comics"})
    attach_from_link(record, "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16",
                      metron=None, covers_dir=tmp_path)
    assert record.publisher == "DC Comics"


def test_attach_from_link_routes_metron_url_to_metron(tmp_path: Path):
    record = _record()
    metron = FakeMetron(issue=_issue())
    attach_from_link(record, "https://metron.cloud/issue/158565/", metron=metron, covers_dir=tmp_path)
    assert metron.by_id_calls == [158565]
    assert record.publisher == "DC Comics"


def test_attach_from_link_metron_url_without_metron_configured_raises(tmp_path: Path):
    record = _record()
    with pytest.raises(LinkAttachError):
        attach_from_link(record, "https://metron.cloud/issue/158565/", metron=None, covers_dir=tmp_path)
