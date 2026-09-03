from library.metadata_sources.google_books import GoogleBooksSource


class FakeResponse:
    status_code = 200

    def __init__(self, items):
        self._items = items

    def raise_for_status(self):
        pass

    def json(self):
        return {"items": self._items}


def test_cover_image_url_scans_past_first_result_with_no_image(monkeypatch):
    """Regression test: the first search result frequently lacks a cover even
    when a later candidate has one (found against real Google Books data)."""
    items = [
        {"volumeInfo": {"title": "Edition A"}},  # no imageLinks
        {"volumeInfo": {"title": "Edition B"}},  # no imageLinks
        {"volumeInfo": {"title": "Edition C", "imageLinks": {"thumbnail": "https://example.com/c.jpg"}}},
    ]
    monkeypatch.setattr(
        "library.http_utils.requests.get",
        lambda *a, **k: FakeResponse(items),
    )
    source = GoogleBooksSource()
    assert source.cover_image_url("Some Title") == "https://example.com/c.jpg"


def test_cover_image_url_returns_none_when_no_candidate_has_image(monkeypatch):
    items = [{"volumeInfo": {"title": "Edition A"}}, {"volumeInfo": {"title": "Edition B"}}]
    monkeypatch.setattr(
        "library.http_utils.requests.get",
        lambda *a, **k: FakeResponse(items),
    )
    source = GoogleBooksSource()
    assert source.cover_image_url("Some Title") is None


def test_lookup_isbn_returns_title_and_fields(monkeypatch):
    items = [{
        "volumeInfo": {
            "title": "Attack on Titan 29",
            "authors": ["Hajime Isayama"],
            "publisher": "National Geographic Books",
            "publishedDate": "2019-12-03",
            "imageLinks": {"thumbnail": "https://example.com/aot29.jpg"},
        }
    }]
    monkeypatch.setattr(
        "library.http_utils.requests.get",
        lambda *a, **k: FakeResponse(items),
    )
    source = GoogleBooksSource()
    result = source.lookup_isbn("9781632368287")
    assert result["title"] == "Attack on Titan 29"
    assert result["author"] == "Hajime Isayama"
    assert result["year"] == 2019
    assert result["_image_url"] == "https://example.com/aot29.jpg"


def test_lookup_isbn_no_results(monkeypatch):
    monkeypatch.setattr(
        "library.http_utils.requests.get",
        lambda *a, **k: FakeResponse([]),
    )
    source = GoogleBooksSource()
    assert source.lookup_isbn("9789999999999") == {}
