from pathlib import Path

import pytest

from library.enrichment import enrich_record
from library.models import ComicRecord


class FakeSource:
    name = "fake"

    def __init__(self, text_fields: dict | None = None, cover_url: str | None = None):
        self._text_fields = text_fields or {}
        self._cover_url = cover_url
        self.search_calls: list[str] = []

    def search(self, title: str, year=None) -> dict:
        self.search_calls.append(title)
        return dict(self._text_fields)

    def cover_image_url(self, title: str, year=None) -> str | None:
        return self._cover_url


def _complete_record(**overrides) -> ComicRecord:
    defaults = dict(
        id="p1", title="Kingdom Come", type="comic", series="Kingdom Come",
        author="Mark Waid", year=1996, publisher="DC Comics", description="A story.",
        formats=["print"],
    )
    defaults.update(overrides)
    return ComicRecord(**defaults)


def test_fetches_cover_when_missing_even_if_text_fields_complete(tmp_path: Path, monkeypatch):
    record = _complete_record(cover_path=None)
    source = FakeSource(cover_url="https://example.com/cover.jpg")

    class FakeResponse:
        content = b"fake-image-bytes"
        headers = {}

        def raise_for_status(self):
            pass

    monkeypatch.setattr("library.enrichment.requests.get", lambda *a, **k: FakeResponse())

    changed = enrich_record(record, [source], tmp_path)

    assert changed is True
    assert record.cover_path == "p1/cover.jpg"
    assert (tmp_path / "p1" / "cover.jpg").read_bytes() == b"fake-image-bytes"
    assert record.metadata_source["cover_path"] == "fake"


def test_skips_cover_fetch_when_already_present(tmp_path: Path, monkeypatch):
    record = _complete_record(cover_path="p1/cover.jpg")
    source = FakeSource(cover_url="https://example.com/cover.jpg")

    def boom(*a, **k):
        raise AssertionError("should not fetch when cover already present")

    monkeypatch.setattr("library.enrichment.requests.get", boom)

    changed = enrich_record(record, [source], tmp_path)
    assert changed is False
    assert record.cover_path == "p1/cover.jpg"


def test_no_op_when_record_fully_complete(tmp_path: Path):
    record = _complete_record(cover_path="p1/cover.jpg")
    source = FakeSource()
    changed = enrich_record(record, [source], tmp_path)
    assert changed is False


def test_manga_search_query_includes_volume_number(tmp_path: Path):
    """A bare series-name query ("Berserk") is ambiguous across many
    editions/languages — including the volume number disambiguates it,
    per the live Google Books check that motivated this."""
    record = ComicRecord(
        id="m1", title="Berserk #1", type="manga", series="Berserk",
        issue_number="01", cover_path="m1/cover.jpg", formats=["digital"],
    )
    source = FakeSource(text_fields={"author": "Kentaro Miura"})

    enrich_record(record, [source], tmp_path)

    assert source.search_calls == ["Berserk Vol. 1"]


def test_comic_search_query_is_series_name_only(tmp_path: Path):
    """Comics don't get the volume-number treatment — Metron's own
    search already disambiguates by series+year internally."""
    record = ComicRecord(
        id="c1", title="Kingdom Come #1", type="comic", series="Kingdom Come",
        issue_number="1", cover_path="c1/cover.jpg", formats=["digital"],
    )
    source = FakeSource(text_fields={"author": "Mark Waid"})

    enrich_record(record, [source], tmp_path)

    assert source.search_calls == ["Kingdom Come"]


def test_cover_fetch_failure_is_swallowed_gracefully(tmp_path: Path, monkeypatch):
    record = _complete_record(cover_path=None)
    source = FakeSource(cover_url="https://example.com/cover.jpg")

    def raise_error(*a, **k):
        raise ConnectionError("network down")

    monkeypatch.setattr("library.enrichment.requests.get", raise_error)

    changed = enrich_record(record, [source], tmp_path)
    assert changed is False
    assert record.cover_path is None
