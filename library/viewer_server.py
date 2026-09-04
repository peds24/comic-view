"""HTTP handler for `comic-library serve`: serves the repo root as static
files (so viewer.html can fetch data/library.json and cover images) exactly
like http.server.SimpleHTTPRequestHandler, plus POST routes that let
viewer.html manually attach a cover image or a specific Comic Geeks issue
to a record, rename a record's title, or delete a record — the only way a
record gets written to (or removed) from the browser, instead of a CLI
import/enrich command.

GET /data/library.json is special-cased to always return `library_path`'s
content, whatever its actual filename — lets `serve --data <file>` point
viewer.html at e.g. library_digital.json without viewer.html knowing about
the swap.
"""
from __future__ import annotations

import base64
import http.server
import json
from pathlib import Path
from typing import Callable

from library.covers import delete_cover_dir
from library.manual_attach import LinkAttachError, attach_cover_bytes, attach_from_link, set_formats, set_title, set_year
from library.store import delete_record, load_library, save_library

_VALID_FORMATS = ("digital", "print")


class ViewerRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        library_path: Path,
        covers_dir: Path,
        **kwargs,
    ) -> None:
        self.library_path = library_path
        self.covers_dir = covers_dir
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        if self.path == "/data/library.json":
            self._serve_library_json()
            return
        super().do_GET()

    def _serve_library_json(self) -> None:
        if not self.library_path.exists():
            self.send_error(404)
            return
        body = self.library_path.read_bytes()
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
            "/api/delete-record": self._delete_record,
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

    def _attach_cover(self, body: dict) -> tuple[int, dict]:
        records = load_library(self.library_path)
        record = records.get(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        image_bytes = base64.b64decode(body["data_base64"])
        attach_cover_bytes(record, image_bytes, body.get("ext") or ".jpg", self.covers_dir)
        save_library(self.library_path, records)
        return 200, {"ok": True, "cover_path": record.cover_path}

    def _attach_link(self, body: dict) -> tuple[int, dict]:
        records = load_library(self.library_path)
        record = records.get(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        try:
            attach_from_link(record, body["url"], covers_dir=self.covers_dir)
        except LinkAttachError as e:
            return 422, {"error": str(e)}

        save_library(self.library_path, records)
        return 200, {"ok": True, "record": record.to_dict()}

    def _update_title(self, body: dict) -> tuple[int, dict]:
        records = load_library(self.library_path)
        record = records.get(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        title = (body.get("title") or "").strip()
        if not title:
            return 400, {"error": "title can't be empty"}

        set_title(record, title)
        save_library(self.library_path, records)
        return 200, {"ok": True, "record": record.to_dict()}

    def _update_year(self, body: dict) -> tuple[int, dict]:
        records = load_library(self.library_path)
        record = records.get(body["id"])
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
        save_library(self.library_path, records)
        return 200, {"ok": True, "record": record.to_dict()}

    def _update_formats(self, body: dict) -> tuple[int, dict]:
        records = load_library(self.library_path)
        record = records.get(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        formats = body.get("formats")
        if not isinstance(formats, list) or not formats:
            return 400, {"error": "formats must be a non-empty list"}
        invalid = [f for f in formats if f not in _VALID_FORMATS]
        if invalid:
            return 400, {"error": f"invalid format(s): {invalid}"}

        set_formats(record, list(dict.fromkeys(formats)))
        save_library(self.library_path, records)
        return 200, {"ok": True, "record": record.to_dict()}

    def _delete_record(self, body: dict) -> tuple[int, dict]:
        records = load_library(self.library_path)
        record = delete_record(records, body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        delete_cover_dir(record.id, self.covers_dir)
        save_library(self.library_path, records)
        return 200, {"ok": True}

    def _respond_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
