"""Walk configured root folders, find archives, and build ComicRecords.

No network calls happen here — only ComicInfo.xml + filename parsing, plus
cover/preview extraction. See enrichment.py for the online lookup pass.
"""
from __future__ import annotations

from pathlib import Path

from library import comicinfo_parser, filename_parser
from library.archive_reader import ArchiveError, extract_cover_and_preview, read_comicinfo_bytes
from library.config import Config, RootConfig
from library.hashing import compute_id
from library.models import ComicRecord

ARCHIVE_EXTENSIONS = {".cbz", ".cbr"}


def find_archives(root: Path) -> list[Path]:
    # Skip hidden dot-files (e.g. macOS "._Name.cbr" AppleDouble resource-fork
    # files created when copying to non-native filesystems like exFAT) — they
    # share the extension but aren't real archives.
    return sorted(
        p
        for p in root.rglob("*")
        if p.suffix.lower() in ARCHIVE_EXTENSIONS and not p.name.startswith(".")
    )


def build_record(path: Path, root: RootConfig, covers_dir: Path) -> ComicRecord:
    comic_id = compute_id(path)

    fields: dict = {}
    sources: dict[str, str] = {}

    filename_fields = filename_parser.parse_filename(path.name)
    for key, value in filename_fields.items():
        fields[key] = value
        sources[key] = "filename"

    comicinfo_bytes = read_comicinfo_bytes(path)
    if comicinfo_bytes:
        comicinfo_fields = comicinfo_parser.parse_comicinfo(comicinfo_bytes)
        for key, value in comicinfo_fields.items():
            fields[key] = value
            sources[key] = "comicinfo"

    cover_filename, preview_filenames = extract_cover_and_preview(path, covers_dir / comic_id)
    cover_path = f"{comic_id}/{cover_filename}" if cover_filename else None
    preview_pages = [f"{comic_id}/{name}" for name in preview_filenames]

    title = fields.pop("title", None) or path.stem

    return ComicRecord(
        id=comic_id,
        title=title,
        type=root.type,
        series=fields.get("series"),
        issue_number=fields.get("issue_number"),
        author=fields.get("author"),
        year=fields.get("year"),
        publisher=fields.get("publisher"),
        description=fields.get("description"),
        cover_path=cover_path,
        preview_pages=preview_pages,
        metadata_source=sources,
    )


def scan_roots(config: Config) -> tuple[list[ComicRecord], list[tuple[Path, str]]]:
    """Returns (records, skipped) — skipped is (path, reason) for archives that
    couldn't be read (e.g. corrupt files), so one bad file doesn't abort the scan.
    """
    covers_dir = config.data_dir / "covers"
    records: list[ComicRecord] = []
    skipped: list[tuple[Path, str]] = []
    for root in config.roots:
        if not root.path.exists():
            continue
        for archive_path in find_archives(root.path):
            try:
                records.append(build_record(archive_path, root, covers_dir))
            except ArchiveError as e:
                skipped.append((archive_path, str(e)))
    return records, skipped
