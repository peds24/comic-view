"""HTTP handler for `comic-library serve`: serves the repo root as static
files (so viewer.html can fetch data/library.json and cover images) exactly
like http.server.SimpleHTTPRequestHandler, plus POST routes that let
viewer.html manually attach a cover image or a specific Comic Geeks issue
to a record, rename a record's title, or delete a record — the only way a
record gets written to (or removed) from the browser, instead of a CLI
import/enrich command.

GET /data/library.json is special-cased to merge `comics_path` and
`manga_path` into one JSON array — lets viewer.html keep fetching a single
URL and filtering by `type` client-side (its Comics/Manga tabs) without
knowing the library is actually stored as two separate files. Each POST
route looks up which of the two files actually holds the given record id
and writes back only that one.
"""
from __future__ import annotations

import base64
import http.server
import json
from pathlib import Path
from typing import Callable

from library.config import Config
from library.covers import delete_cover_dir
from library.manual_attach import (
    LinkAttachError,
    attach_cover_bytes,
    attach_from_link,
    set_formats,
    set_status,
    set_title,
    set_year,
)
from library.metadata_sources.google_books import GoogleBooksSource
from library.metadata_sources.metron import MetronSource
from library.metadata_sources.open_library import OpenLibrarySource
from library.models import ComicRecord
from library.quick_add import QuickAddError, add_comic, add_manga
from library.store import delete_record, load_library, save_library

_VALID_FORMATS = ("digital", "print")
_VALID_STATUSES = ("read", "unread")


class ViewerRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        comics_path: Path,
        manga_path: Path,
        covers_dir: Path,
        config: Config,
        **kwargs,
    ) -> None:
        self.comics_path = comics_path
        self.manga_path = manga_path
        self.covers_dir = covers_dir
        self.config = config
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        if self.path == "/data/library.json":
            self._serve_library_json()
            return
        super().do_GET()

    def _serve_library_json(self) -> None:
        if not self.comics_path.exists() and not self.manga_path.exists():
            self.send_error(404)
            return
        records: list[dict] = []
        for path in (self.comics_path, self.manga_path):
            if path.exists():
                records.extend(json.loads(path.read_text()))
        body = json.dumps(records).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        routes: dict[str, Callable[[dict], tuple[int, dict]]] = {
            "/api/attach-cover": self._attach_cover,
            "/api/attach-link": self._attach_link,
            "/api/update-title": self._update_title,
            "/api/update-year": self._update_year,
            "/api/update-formats": self._update_formats,
            "/api/update-status": self._update_status,
            "/api/delete-record": self._delete_record,
            "/api/add-comic": self._add_comic,
            "/api/add-manga": self._add_manga,
        }
        route = routes.get(self.path)
        if route is None:
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            status, payload = route(body)
        except Exception as e:
            status, payload = 400, {"error": str(e)}
        self._respond_json(status, payload)

    def _find_record(self, record_id: str) -> tuple[ComicRecord | None, dict[str, ComicRecord], Path | None]:
        """Loads both library files and returns the record, the dict it
        lives in, and that dict's backing path — so a caller can mutate the
        dict and save back only that one file. (None, {}, None) if the id
        isn't in either file."""
        for path in (self.comics_path, self.manga_path):
            records = load_library(path)
            if record_id in records:
                return records[record_id], records, path
        return None, {}, None

    def _attach_cover(self, body: dict) -> tuple[int, dict]:
        record, records, path = self._find_record(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        image_bytes = base64.b64decode(body["data_base64"])
        attach_cover_bytes(record, image_bytes, body.get("ext") or ".jpg", self.covers_dir)
        save_library(path, records)
        return 200, {"ok": True, "cover_path": record.cover_path}

    def _attach_link(self, body: dict) -> tuple[int, dict]:
        record, records, path = self._find_record(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        try:
            attach_from_link(record, body["url"], covers_dir=self.covers_dir)
        except LinkAttachError as e:
            return 422, {"error": str(e)}

        save_library(path, records)
        return 200, {"ok": True, "record": record.to_dict()}

    def _update_title(self, body: dict) -> tuple[int, dict]:
        record, records, path = self._find_record(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        title = (body.get("title") or "").strip()
        if not title:
            return 400, {"error": "title can't be empty"}

        set_title(record, title)
        save_library(path, records)
        return 200, {"ok": True, "record": record.to_dict()}

    def _update_year(self, body: dict) -> tuple[int, dict]:
        record, records, path = self._find_record(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        raw = body.get("year")
        if raw in (None, ""):
            year = None
        else:
            try:
                year = int(raw)
            except (TypeError, ValueError):
                return 400, {"error": "year must be a whole number"}
            if not (1800 <= year <= 2100):
                return 400, {"error": "year looks out of range"}

        set_year(record, year)
        save_library(path, records)
        return 200, {"ok": True, "record": record.to_dict()}

    def _validate_formats(self, body: dict) -> list[str] | None:
        formats = body.get("formats")
        if not isinstance(formats, list) or not formats:
            return None
        if any(f not in _VALID_FORMATS for f in formats):
            return None
        return list(dict.fromkeys(formats))

    def _update_formats(self, body: dict) -> tuple[int, dict]:
        record, records, path = self._find_record(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        formats = self._validate_formats(body)
        if formats is None:
            return 400, {"error": "formats must be a non-empty list of 'digital'/'print'"}

        set_formats(record, formats)
        save_library(path, records)
        return 200, {"ok": True, "record": record.to_dict()}

    def _update_status(self, body: dict) -> tuple[int, dict]:
        record, records, path = self._find_record(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        status = body.get("status")
        if status not in _VALID_STATUSES:
            return 400, {"error": f"status must be one of {_VALID_STATUSES}"}

        set_status(record, status)
        save_library(path, records)
        return 200, {"ok": True, "record": record.to_dict()}

    def _delete_record(self, body: dict) -> tuple[int, dict]:
        record, records, path = self._find_record(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        delete_record(records, record.id)
        delete_cover_dir(record.id, self.covers_dir)
        save_library(path, records)
        return 200, {"ok": True}

    def _add_comic(self, body: dict) -> tuple[int, dict]:
        formats = self._validate_formats(body)
        if formats is None:
            return 400, {"error": "formats must be a non-empty list of 'digital'/'print'"}

        config = self.config
        metron = MetronSource(config.metron.username, config.metron.password) if config.metron.is_configured else None
        google_books = GoogleBooksSource(config.google_books.api_key)
        open_library = OpenLibrarySource()

        records = load_library(self.comics_path)
        try:
            result = add_comic(
                records, body["input"], formats,
                metron=metron, google_books=google_books, open_library=open_library, covers_dir=self.covers_dir,
            )
        except QuickAddError as e:
            return 422, {"error": str(e)}

        save_library(self.comics_path, records)
        return 200, {"ok": True, "merged": result.merged, "record": result.record.to_dict()}

    def _add_manga(self, body: dict) -> tuple[int, dict]:
        formats = self._validate_formats(body)
        if formats is None:
            return 400, {"error": "formats must be a non-empty list of 'digital'/'print'"}

        config = self.config
        google_books = GoogleBooksSource(config.google_books.api_key)
        open_library = OpenLibrarySource()

        records = load_library(self.manga_path)
        try:
            result = add_manga(
                records, body["input"], formats,
                google_books=google_books, open_library=open_library, covers_dir=self.covers_dir,
            )
        except QuickAddError as e:
            return 422, {"error": str(e)}

        save_library(self.manga_path, records)
        return 200, {"ok": True, "merged": result.merged, "record": result.record.to_dict()}

    def _respond_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
