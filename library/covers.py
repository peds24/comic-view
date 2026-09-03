"""Shared helpers for writing a record's cover image under
data/covers/<id>/ — used by the automatic importer, and by manually
attaching a cover or Metron issue to a record."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from library.http_utils import get_with_retry
from library.models import ComicRecord

_DEFAULT_COVER_EXT = ".jpg"


def save_cover_bytes(record: ComicRecord, data: bytes, ext: str, source_name: str, covers_dir: Path) -> None:
    """Writes `data` as this record's cover, overwriting any existing one."""
    ext = ext if ext.startswith(".") else f".{ext}"
    dest_dir = covers_dir / record.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / f"cover{ext}").write_bytes(data)
    record.cover_path = f"{record.id}/cover{ext}"
    record.metadata_source["cover_path"] = source_name


def download_cover(record: ComicRecord, url: str, source_name: str, covers_dir: Path) -> bool:
    """Fetches `url` and saves it as this record's cover. Returns False
    (leaving the record untouched) if the request fails."""
    try:
        resp = get_with_retry(url, timeout=10)
        resp.raise_for_status()
    except Exception:
        return False
    ext = Path(urlparse(url).path).suffix or _DEFAULT_COVER_EXT
    save_cover_bytes(record, resp.content, ext, source_name, covers_dir)
    return True
