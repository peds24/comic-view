"""Read CBZ/CBR archives: find ComicInfo.xml and extract the cover + preview pages.

This is the only place archives are opened. It never extracts more than the
first few pages — the rest of the book is read (for listing) but never
copied out.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import rarfile

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PREVIEW_PAGE_COUNT = 4  # 1 cover + 3 preview pages


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
        return _ZipArchive(path)
    if suffix == ".cbr":
        return _RarArchive(path)
    raise ArchiveError(f"Unsupported archive type: {path}")


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


def extract_cover_and_preview(path: Path, dest_dir: Path) -> tuple[str | None, list[str]]:
    """Extract the cover (first image) and up to 3 following pages to dest_dir.

    Returns (cover_filename, [preview_page_filenames]), relative to dest_dir.
    """
    archive = _open_archive(path)
    try:
        image_names = sorted(
            n for n in archive.namelist() if Path(n).suffix.lower() in IMAGE_EXTENSIONS
        )
        if not image_names:
            return None, []

        dest_dir.mkdir(parents=True, exist_ok=True)

        selected = image_names[:PREVIEW_PAGE_COUNT]
        cover_filename: str | None = None
        preview_filenames: list[str] = []

        for i, name in enumerate(selected):
            ext = Path(name).suffix.lower()
            data = archive.read(name)
            if i == 0:
                out_name = f"cover{ext}"
                cover_filename = out_name
            else:
                out_name = f"page-{i:02d}{ext}"
                preview_filenames.append(out_name)
            (dest_dir / out_name).write_bytes(data)

        return cover_filename, preview_filenames
    finally:
        archive.close()
