from pathlib import Path

from library.config import Config, GoogleBooksConfig, MetronConfig, RootConfig
from library.models import ComicRecord
from library import scanner


def _config(tmp_path: Path, roots: list[RootConfig]) -> Config:
    return Config(
        roots=roots,
        metron=MetronConfig(),
        google_books=GoogleBooksConfig(),
        data_dir=tmp_path / "data",
    )


def test_list_archives_finds_files_across_roots_and_skips_missing_root(tmp_path):
    comics_root = tmp_path / "comics"
    comics_root.mkdir()
    (comics_root / "Batman 001.cbz").write_bytes(b"")
    (comics_root / "Batman 002.cbr").write_bytes(b"")
    (comics_root / "notes.txt").write_bytes(b"")

    manga_root = tmp_path / "manga"  # left uncreated — should be skipped, not raise

    config = _config(
        tmp_path,
        [
            RootConfig(path=comics_root, type="comic"),
            RootConfig(path=manga_root, type="manga"),
        ],
    )

    archives = scanner.list_archives(config)

    assert len(archives) == 2
    assert all(root.type == "comic" for _path, root in archives)


def test_scan_roots_calls_on_progress_once_per_archive(tmp_path, monkeypatch):
    comics_root = tmp_path / "comics"
    comics_root.mkdir()
    for name in ("A.cbz", "B.cbz", "C.cbz"):
        (comics_root / name).write_bytes(b"")

    config = _config(tmp_path, [RootConfig(path=comics_root, type="comic")])

    monkeypatch.setattr(
        scanner,
        "build_record",
        lambda path, root, covers_dir: ComicRecord(id=path.name, title=path.name, type="comic"),
    )

    calls: list[tuple[int, int]] = []
    records, skipped = scanner.scan_roots(config, on_progress=lambda completed, total: calls.append((completed, total)))

    assert len(records) == 3
    assert skipped == []
    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_scan_roots_works_without_on_progress(tmp_path):
    config = _config(tmp_path, [RootConfig(path=tmp_path / "missing", type="comic")])
    records, skipped = scanner.scan_roots(config)
    assert records == []
    assert skipped == []


def test_scan_roots_skips_files_that_raise_os_error(tmp_path, monkeypatch):
    comics_root = tmp_path / "comics"
    comics_root.mkdir()
    (comics_root / "A.cbz").write_bytes(b"")
    (comics_root / "B.cbz").write_bytes(b"")

    config = _config(tmp_path, [RootConfig(path=comics_root, type="comic")])

    def fake_build_record(path, root, covers_dir):
        if path.name == "A.cbz":
            raise TimeoutError("cloud file not downloaded")
        return ComicRecord(id=path.name, title=path.name, type="comic")

    monkeypatch.setattr(scanner, "build_record", fake_build_record)

    records, skipped = scanner.scan_roots(config)

    assert len(records) == 1
    assert len(skipped) == 1
    assert skipped[0][0].name == "A.cbz"
