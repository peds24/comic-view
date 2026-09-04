"""Read CBZ/CBR archives: find ComicInfo.xml and extract the cover image.

This is the only place archives are opened. It never extracts more than the
cover — the rest of the book is read (for listing) but never copied out.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import rarfile

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class ArchiveError(Exception):
    pass


class _ZipArchive:
    def __init__(self, path: Path):
        self._zf = zipfile.ZipFile(path)

    def namelist(self) -> list[str]:
        return [n for n in self._zf.namelist() if not n.endswith("/")]

    def read(self, name: str) -> bytes:
        return self._zf.read(name)

    def close(self) -> None:
        self._zf.close()


class _RarArchive:
    def __init__(self, path: Path):
        self._rf = rarfile.RarFile(path)

    def namelist(self) -> list[str]:
        return [n for n in self._rf.namelist() if not n.endswith("/")]

    def read(self, name: str) -> bytes:
        return self._rf.read(name)

    def close(self) -> None:
        self._rf.close()


def _open_archive(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".cbz":
        return _open_as_zip(path)
    if suffix == ".cbr":
        try:
            return _RarArchive(path)
        except rarfile.NotRarFile:
            # Some "cbr" files in the wild are actually mislabeled ZIPs.
            try:
                return _open_as_zip(path)
            except ArchiveError:
                raise ArchiveError(f"{path} is neither a valid RAR nor ZIP archive")
        except rarfile.Error as e:
            raise ArchiveError(f"Failed to open {path}: {e}") from e
    raise ArchiveError(f"Unsupported archive type: {path}")


def _open_as_zip(path: Path) -> "_ZipArchive":
    try:
        return _ZipArchive(path)
    except zipfile.BadZipFile as e:
        raise ArchiveError(f"Failed to open {path}: {e}") from e


def read_comicinfo_bytes(path: Path) -> bytes | None:
    """Return the raw bytes of ComicInfo.xml inside the archive, if present."""
    archive = _open_archive(path)
    try:
        for name in archive.namelist():
            if Path(name).name.lower() == "comicinfo.xml":
                return archive.read(name)
        return None
    finally:
        archive.close()


def extract_cover(path: Path, dest_dir: Path) -> str | None:
    """Extract the cover (first image, by name order) to dest_dir.

    Returns the cover filename, relative to dest_dir, or None if the
    archive has no images.
    """
    archive = _open_archive(path)
    try:
        image_names = sorted(
            n for n in archive.namelist() if Path(n).suffix.lower() in IMAGE_EXTENSIONS
        )
        if not image_names:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(image_names[0]).suffix.lower()
        data = archive.read(image_names[0])
        cover_filename = f"cover{ext}"
        (dest_dir / cover_filename).write_bytes(data)

        return cover_filename
    finally:
        archive.close()
