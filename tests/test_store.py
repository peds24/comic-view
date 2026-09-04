from pathlib import Path

from library.models import ComicRecord
from library.store import delete_record, load_library, merge_record, save_library


def make_record(id_: str, status: str = "unread") -> ComicRecord:
    return ComicRecord(id=id_, title=f"Comic {id_}", type="comic", status=status)


def test_merge_adds_new_record():
    records: dict[str, ComicRecord] = {}
    added = merge_record(records, make_record("a"))
    assert added is True
    assert "a" in records


def test_merge_does_not_overwrite_existing_record():
    records = {"a": make_record("a", status="read")}
    added = merge_record(records, make_record("a", status="unread"))
    assert added is False
    assert records["a"].status == "read"


def test_save_and_load_roundtrip(tmp_path: Path):
    library_path = tmp_path / "library.json"
    records = {"a": make_record("a", status="read")}
    save_library(library_path, records)

    loaded = load_library(library_path)
    assert loaded["a"].status == "read"
    assert loaded["a"].title == "Comic a"


def test_load_missing_file_returns_empty(tmp_path: Path):
    assert load_library(tmp_path / "does-not-exist.json") == {}


def test_rescan_preserves_status_after_reload(tmp_path: Path):
    library_path = tmp_path / "library.json"
    save_library(library_path, {"a": make_record("a", status="unread")})

    existing = load_library(library_path)
    existing["a"].status = "read"
    save_library(library_path, existing)

    reloaded = load_library(library_path)
    merge_record(reloaded, make_record("a", status="unread"))  # simulate rescan finding same file
    assert reloaded["a"].status == "read"


def test_delete_record_removes_and_returns_it():
    records = {"a": make_record("a")}
    deleted = delete_record(records, "a")
    assert deleted is not None
    assert deleted.id == "a"
    assert "a" not in records


def test_delete_record_missing_id_returns_none():
    records = {"a": make_record("a")}
    assert delete_record(records, "nope") is None
    assert "a" in records
