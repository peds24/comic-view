import zipfile
from pathlib import Path

import pytest

from library.archive_reader import ArchiveError, extract_cover, read_comicinfo_bytes


def _make_cbz(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_read_comicinfo_bytes_finds_it_regardless_of_position(tmp_path: Path):
    archive = tmp_path / "Batman #1.cbz"
    _make_cbz(
        archive,
        {
            "010.jpg": b"cover-bytes",
            "020.jpg": b"page-bytes",
            "ComicInfo.xml": b"<ComicInfo><Title>Batman #1</Title></ComicInfo>",
        },
    )

    assert read_comicinfo_bytes(archive) == b"<ComicInfo><Title>Batman #1</Title></ComicInfo>"


def test_read_comicinfo_bytes_returns_none_when_absent(tmp_path: Path):
    archive = tmp_path / "Batman #1.cbz"
    _make_cbz(archive, {"010.jpg": b"cover-bytes"})

    assert read_comicinfo_bytes(archive) is None


def test_extract_cover_writes_only_the_first_image_by_name(tmp_path: Path):
    archive = tmp_path / "Batman #1.cbz"
    _make_cbz(
        archive,
        {
            "020.jpg": b"page-two",
            "010.jpg": b"cover-bytes",
            "030.jpg": b"page-three",
            "ComicInfo.xml": b"<ComicInfo/>",
        },
    )
    dest_dir = tmp_path / "out"

    cover_filename = extract_cover(archive, dest_dir)

    assert cover_filename == "cover.jpg"
    assert (dest_dir / "cover.jpg").read_bytes() == b"cover-bytes"
    # Nothing else was extracted.
    assert list(dest_dir.iterdir()) == [dest_dir / "cover.jpg"]


def test_extract_cover_ignores_non_image_entries(tmp_path: Path):
    archive = tmp_path / "Batman #1.cbz"
    _make_cbz(
        archive,
        {
            "ComicInfo.xml": b"<ComicInfo/>",
            "010.jpg": b"cover-bytes",
        },
    )
    dest_dir = tmp_path / "out"

    cover_filename = extract_cover(archive, dest_dir)

    assert cover_filename == "cover.jpg"


def test_extract_cover_returns_none_when_no_images(tmp_path: Path):
    archive = tmp_path / "Empty.cbz"
    _make_cbz(archive, {"ComicInfo.xml": b"<ComicInfo/>"})
    dest_dir = tmp_path / "out"

    cover_filename = extract_cover(archive, dest_dir)

    assert cover_filename is None
    assert not dest_dir.exists()


def test_cbr_that_is_actually_a_zip_is_read_as_zip(tmp_path: Path):
    archive = tmp_path / "Mislabeled.cbr"
    _make_cbz(archive, {"010.jpg": b"cover-bytes"})
    dest_dir = tmp_path / "out"

    cover_filename = extract_cover(archive, dest_dir)

    assert cover_filename == "cover.jpg"
    assert (dest_dir / "cover.jpg").read_bytes() == b"cover-bytes"


def test_corrupt_archive_raises_archive_error(tmp_path: Path):
    archive = tmp_path / "Corrupt.cbz"
    archive.write_bytes(b"not a real archive")

    with pytest.raises(ArchiveError):
        read_comicinfo_bytes(archive)


def test_unsupported_extension_raises_archive_error(tmp_path: Path):
    archive = tmp_path / "Batman.txt"
    archive.write_bytes(b"whatever")

    with pytest.raises(ArchiveError):
        read_comicinfo_bytes(archive)
