"""HTTP handler for `comic-library serve`: serves the repo root as static
files (so viewer.html can fetch data/library.json and cover images) exactly
like http.server.SimpleHTTPRequestHandler, plus two POST routes that let
viewer.html manually attach a cover image or a specific Comic Geeks issue
to a record — the only way a record gets written to from the browser,
instead of a CLI import/enrich command.
"""
from __future__ import annotations

import base64
import http.server
import json
from pathlib import Path
from typing import Callable

from library.manual_attach import LinkAttachError, attach_cover_bytes, attach_from_link
from library.store import load_library, save_library


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

    def do_POST(self) -> None:
        routes: dict[str, Callable[[dict], tuple[int, dict]]] = {
            "/api/attach-cover": self._attach_cover,
            "/api/attach-link": self._attach_link,
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

    def _respond_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
