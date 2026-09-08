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

    comics_path = tmp_path / "library_comics.json"
    manga_path = tmp_path / "library_manga.json"
    covers_dir = tmp_path / "covers"
    save_library(comics_path, {
        "upc-1": ComicRecord(id="upc-1", title="Absolute Batman #16 2nd Printing", type="comic", formats=["print"]),
    })
    save_library(manga_path, {
        "isbn-1": ComicRecord(id="isbn-1", title="Berserk, Vol. 1", type="manga", formats=["digital"]),
    })

    handler = functools.partial(
        ViewerRequestHandler,
        directory=str(tmp_path),
        comics_path=comics_path,
        manga_path=manga_path,
        covers_dir=covers_dir,
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, comics_path, manga_path
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


def _get(port: int, path: str) -> tuple[int, bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, body


def test_get_library_json_merges_comics_and_manga(server):
    httpd, _, _ = server
    port = httpd.server_address[1]

    status, body = _get(port, "/data/library.json")

    assert status == 200
    records = json.loads(body)
    ids = {r["id"] for r in records}
    assert ids == {"upc-1", "isbn-1"}


def test_attach_cover_endpoint_writes_file_and_updates_library(server):
    httpd, comics_path, _ = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/attach-cover", {
        "id": "upc-1",
        "ext": ".jpg",
        "data_base64": base64.b64encode(b"real-image-bytes").decode(),
    })

    assert status == 200
    assert data["ok"] is True
    assert data["cover_path"] == "upc-1/cover.jpg"

    records = load_library(comics_path)
    assert records["upc-1"].cover_path == "upc-1/cover.jpg"
    assert records["upc-1"].metadata_source["cover_path"] == "manual"


def test_attach_cover_endpoint_unknown_id_returns_404(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/attach-cover", {"id": "nope", "data_base64": ""})
    assert status == 404
    assert "error" in data


def test_attach_link_endpoint_rejects_non_comic_geeks_url(server):
    httpd, _, _ = server
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
    httpd, comics_path, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/attach-link", {
        "id": "upc-1", "url": "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16",
    })
    assert status == 200
    assert data["ok"] is True
    assert data["record"]["title"] == "Absolute Batman #16 2nd Printing"  # untouched
    assert data["record"]["publisher"] == "DC Comics"
    assert load_library(comics_path)["upc-1"].publisher == "DC Comics"


def test_update_title_endpoint(server):
    httpd, comics_path, _ = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/update-title", {"id": "upc-1", "title": "Absolute Batman #16"})

    assert status == 200
    assert data["record"]["title"] == "Absolute Batman #16"
    records = load_library(comics_path)
    assert records["upc-1"].title == "Absolute Batman #16"
    assert records["upc-1"].metadata_source["title"] == "manual"


def test_update_title_endpoint_rejects_blank_title(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/update-title", {"id": "upc-1", "title": "   "})
    assert status == 400
    assert "error" in data


def test_update_title_endpoint_unknown_id_returns_404(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/update-title", {"id": "nope", "title": "X"})
    assert status == 404


def test_update_title_on_manga_record_only_touches_manga_file(server):
    httpd, comics_path, manga_path = server
    port = httpd.server_address[1]
    comics_before = comics_path.read_text()

    status, data = _post(port, "/api/update-title", {"id": "isbn-1", "title": "Berserk, Vol. 1 (Deluxe)"})

    assert status == 200
    assert load_library(manga_path)["isbn-1"].title == "Berserk, Vol. 1 (Deluxe)"
    assert load_library(comics_path)["upc-1"].title == "Absolute Batman #16 2nd Printing"
    assert comics_path.read_text() == comics_before  # comics file untouched byte-for-byte


def test_update_year_endpoint(server):
    httpd, comics_path, _ = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/update-year", {"id": "upc-1", "year": 2016})

    assert status == 200
    assert data["record"]["year"] == 2016
    records = load_library(comics_path)
    assert records["upc-1"].year == 2016
    assert records["upc-1"].metadata_source["year"] == "manual"


def test_update_year_endpoint_clears_year_on_blank(server):
    httpd, comics_path, _ = server
    port = httpd.server_address[1]
    _post(port, "/api/update-year", {"id": "upc-1", "year": 2016})

    status, data = _post(port, "/api/update-year", {"id": "upc-1", "year": ""})

    assert status == 200
    assert data["record"]["year"] is None
    assert "year" not in load_library(comics_path)["upc-1"].metadata_source


def test_update_year_endpoint_rejects_non_numeric(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/update-year", {"id": "upc-1", "year": "not-a-year"})
    assert status == 400
    assert "error" in data


def test_update_year_endpoint_rejects_out_of_range(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/update-year", {"id": "upc-1", "year": 9999})
    assert status == 400
    assert "error" in data


def test_update_formats_endpoint(server):
    httpd, comics_path, _ = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/update-formats", {"id": "upc-1", "formats": ["digital", "print"]})

    assert status == 200
    assert data["record"]["formats"] == ["digital", "print"]
    assert load_library(comics_path)["upc-1"].formats == ["digital", "print"]


def test_update_formats_endpoint_rejects_empty_list(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/update-formats", {"id": "upc-1", "formats": []})
    assert status == 400
    assert "error" in data


def test_update_formats_endpoint_rejects_invalid_format(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/update-formats", {"id": "upc-1", "formats": ["ebook"]})
    assert status == 400
    assert "error" in data


def test_update_status_endpoint(server):
    httpd, comics_path, _ = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/update-status", {"id": "upc-1", "status": "read"})

    assert status == 200
    assert data["record"]["status"] == "read"
    assert load_library(comics_path)["upc-1"].status == "read"


def test_update_status_endpoint_rejects_invalid_status(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/update-status", {"id": "upc-1", "status": "reading"})
    assert status == 400
    assert "error" in data


def test_update_status_endpoint_unknown_id_returns_404(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/update-status", {"id": "nope", "status": "read"})
    assert status == 404
    assert "error" in data


def test_delete_record_endpoint_removes_record_and_cover(server, tmp_path):
    httpd, comics_path, _ = server
    port = httpd.server_address[1]
    covers_dir = tmp_path / "covers"
    cover_dir = covers_dir / "upc-1"
    cover_dir.mkdir(parents=True)
    (cover_dir / "cover.jpg").write_bytes(b"bytes")

    status, data = _post(port, "/api/delete-record", {"id": "upc-1"})

    assert status == 200
    assert data["ok"] is True
    assert "upc-1" not in load_library(comics_path)
    assert not cover_dir.exists()


def test_delete_record_on_manga_leaves_comics_file_untouched(server):
    httpd, comics_path, manga_path = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/delete-record", {"id": "isbn-1"})

    assert status == 200
    assert "isbn-1" not in load_library(manga_path)
    assert "upc-1" in load_library(comics_path)


def test_delete_record_endpoint_unknown_id_returns_404(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    status, data = _post(port, "/api/delete-record", {"id": "nope"})
    assert status == 404
    assert "error" in data


def test_unknown_route_returns_404(server):
    httpd, _, _ = server
    port = httpd.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/api/nonexistent", body=b"{}")
    resp = conn.getresponse()
    resp.read()
    conn.close()
    assert resp.status == 404
