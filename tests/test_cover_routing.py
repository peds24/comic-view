from pathlib import Path

from library.enrichment import refetch_physical_covers
from library.models import ComicRecord


class FakeSource:
    def __init__(self, name: str, cover_url: str | None):
        self.name = name
        self._cover_url = cover_url

    def search(self, title, year=None):
        return {}

    def cover_image_url(self, title, year=None):
        return self._cover_url


class FakeResponse:
    content = b"fake-bytes"

    def raise_for_status(self):
        pass


def _comic(**overrides):
    defaults = dict(id="p1", title="Batman #9", type="comic", issue_number="9", formats=["print"])
    defaults.update(overrides)
    return ComicRecord(**defaults)


def test_single_issue_comic_prefers_metron(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.enrichment.requests.get", lambda *a, **k: FakeResponse())
    metron = FakeSource("metron", "https://example.com/metron.jpg")
    google = FakeSource("google_books", "https://example.com/google.jpg")
    records = {"p1": _comic()}

    refetch_physical_covers(records, [metron, google], tmp_path)

    assert records["p1"].metadata_source["cover_path"] == "metron"


def test_tpb_prefers_google_books(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.enrichment.requests.get", lambda *a, **k: FakeResponse())
    metron = FakeSource("metron", "https://example.com/metron.jpg")
    google = FakeSource("google_books", "https://example.com/google.jpg")
    records = {"p1": _comic(title="Batman: The Long Halloween TP 14th Printing", issue_number=None)}

    refetch_physical_covers(records, [metron, google], tmp_path)

    assert records["p1"].metadata_source["cover_path"] == "google_books"


def test_annual_prefers_google_books():
    from library.enrichment import _is_single_issue_comic
    record = _comic(title="Absolute Batman 2025 Annual #1", issue_number="1")
    assert _is_single_issue_comic(record) is False


def test_manga_prefers_google_books(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.enrichment.requests.get", lambda *a, **k: FakeResponse())
    metron = FakeSource("metron", "https://example.com/metron.jpg")
    google = FakeSource("google_books", "https://example.com/google.jpg")
    records = {"p1": ComicRecord(
        id="p1", title="Attack on Titan 29", type="manga", issue_number="29", formats=["print"],
    )}

    refetch_physical_covers(records, [metron, google], tmp_path)

    assert records["p1"].metadata_source["cover_path"] == "google_books"


def test_preferred_source_failure_falls_back(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.enrichment.requests.get", lambda *a, **k: FakeResponse())
    metron = FakeSource("metron", None)  # Metron has nothing for this issue
    google = FakeSource("google_books", "https://example.com/google.jpg")
    records = {"p1": _comic()}  # single issue -> prefers metron, but must fall back

    refetch_physical_covers(records, [metron, google], tmp_path)

    assert records["p1"].metadata_source["cover_path"] == "google_books"
    assert records["p1"].cover_path == "p1/cover.jpg"


def test_never_touches_digital_or_merged_records(tmp_path: Path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should never fetch for digital/merged records")
    monkeypatch.setattr("library.enrichment.requests.get", boom)

    metron = FakeSource("metron", "https://example.com/metron.jpg")
    google = FakeSource("google_books", "https://example.com/google.jpg")
    records = {
        "d1": ComicRecord(id="d1", title="Digital Only", type="comic", formats=["digital"], cover_path=None),
        "d2": ComicRecord(id="d2", title="Both", type="comic", formats=["digital", "print"], cover_path=None),
    }

    updated = refetch_physical_covers(records, [metron, google], tmp_path)

    assert updated == 0
    assert records["d1"].cover_path is None
    assert records["d2"].cover_path is None


def test_overwrites_existing_physical_only_cover(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.enrichment.requests.get", lambda *a, **k: FakeResponse())
    metron = FakeSource("metron", "https://example.com/metron.jpg")
    google = FakeSource("google_books", "https://example.com/google.jpg")
    records = {"p1": _comic(cover_path="p1/cover.png", metadata_source={"cover_path": "google_books"})}

    refetch_physical_covers(records, [metron, google], tmp_path)

    assert records["p1"].metadata_source["cover_path"] == "metron"
