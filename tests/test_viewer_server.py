import base64
import functools
import http.client
import http.server
import json
import threading

import pytest

from library.models import ComicRecord
from library.store import load_library, save_library
from library.viewer_server import ViewerRequestHandler


class FakeCoverResponse:
    content = b"fake-cover-bytes"

    def raise_for_status(self):
        pass


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    library_path = tmp_path / "library.json"
    covers_dir = tmp_path / "covers"
    records = {
        "upc-1": ComicRecord(id="upc-1", title="Absolute Batman #16 2nd Printing", type="comic", formats=["print"]),
    }
    save_library(library_path, records)

    handler = functools.partial(
        ViewerRequestHandler,
        directory=str(tmp_path),
        library_path=library_path,
        covers_dir=covers_dir,
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, library_path
    finally:
        httpd.shutdown()
        thread.join()


def _post(port: int, path: str, payload: dict) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps(payload).encode()
    conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return resp.status, data


def test_attach_cover_endpoint_writes_file_and_updates_library(server):
    httpd, library_path = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/attach-cover", {
        "id": "upc-1",
        "ext": ".jpg",
        "data_base64": base64.b64encode(b"real-image-bytes").decode(),
    })

    assert status == 200
    assert data["ok"] is True
    assert data["cover_path"] == "upc-1/cover.jpg"

    records = load_library(library_path)
    assert records["upc-1"].cover_path == "upc-1/cover.jpg"
    assert records["upc-1"].metadata_source["cover_path"] == "manual"


def test_attach_cover_endpoint_unknown_id_returns_404(server):
    httpd, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/attach-cover", {"id": "nope", "data_base64": ""})
    assert status == 404
    assert "error" in data


def test_attach_link_endpoint_rejects_non_comic_geeks_url(server):
    httpd, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/attach-link", {"id": "upc-1", "url": "https://metron.cloud/issue/158565/"})
    assert status == 422
    assert "error" in data


def test_attach_link_endpoint_comic_geeks_success(server, monkeypatch):
    monkeypatch.setattr(
        "library.metadata_sources.comic_geeks.fetch_issue",
        lambda url: {
            "series": "Absolute Batman", "issue_number": "16", "publisher": "DC Comics", "year": 2026,
        },
    )
    httpd, library_path = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/attach-link", {
        "id": "upc-1", "url": "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16",
    })
    assert status == 200
    assert data["ok"] is True
    assert data["record"]["title"] == "Absolute Batman #16 2nd Printing"  # untouched
    assert data["record"]["publisher"] == "DC Comics"
    assert load_library(library_path)["upc-1"].publisher == "DC Comics"


def test_unknown_route_returns_404(server):
    httpd, _ = server
    port = httpd.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/api/nonexistent", body=b"{}")
    resp = conn.getresponse()
    resp.read()
    conn.close()
    assert resp.status == 404
