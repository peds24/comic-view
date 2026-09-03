from pathlib import Path

from library.covers import download_cover, save_cover_bytes
from library.models import ComicRecord


class FakeResponse:
    def __init__(self, content=b"fake-bytes"):
        self.content = content

    def raise_for_status(self):
        pass


def _record(**overrides):
    defaults = dict(id="p1", title="Something", type="comic", formats=["print"])
    defaults.update(overrides)
    return ComicRecord(**defaults)


def test_save_cover_bytes_writes_file_and_updates_record(tmp_path: Path):
    record = _record()
    save_cover_bytes(record, b"raw-bytes", "jpg", "manual", tmp_path)

    assert (tmp_path / "p1" / "cover.jpg").read_bytes() == b"raw-bytes"
    assert record.cover_path == "p1/cover.jpg"
    assert record.metadata_source["cover_path"] == "manual"


def test_save_cover_bytes_normalizes_extension_without_leading_dot(tmp_path: Path):
    record = _record()
    save_cover_bytes(record, b"x", "png", "manual", tmp_path)
    assert record.cover_path == "p1/cover.png"


def test_save_cover_bytes_overwrites_existing_cover(tmp_path: Path):
    record = _record(cover_path="p1/cover.png", metadata_source={"cover_path": "metron"})
    save_cover_bytes(record, b"new-bytes", ".jpg", "manual", tmp_path)
    assert record.cover_path == "p1/cover.jpg"
    assert record.metadata_source["cover_path"] == "manual"
    assert (tmp_path / "p1" / "cover.jpg").read_bytes() == b"new-bytes"


def test_download_cover_success(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeResponse(b"downloaded"))
    record = _record()
    assert download_cover(record, "https://example.com/cover.jpg", "metron", tmp_path) is True
    assert record.cover_path == "p1/cover.jpg"
    assert record.metadata_source["cover_path"] == "metron"
    assert (tmp_path / "p1" / "cover.jpg").read_bytes() == b"downloaded"


def test_download_cover_failure_leaves_record_untouched(tmp_path: Path, monkeypatch):
    def raise_error(*a, **k):
        raise ConnectionError("network down")

    monkeypatch.setattr("library.covers.get_with_retry", raise_error)
    record = _record()
    assert download_cover(record, "https://example.com/cover.jpg", "metron", tmp_path) is False
    assert record.cover_path is None
