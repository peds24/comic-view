from library.metadata_sources.open_library import OpenLibrarySource


class FakeResponse:
    status_code = 200

    def __init__(self, data=None):
        self._data = data or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_lookup_isbn_returns_title_author_publisher_year_and_cover(monkeypatch):
    monkeypatch.setattr(
        "library.metadata_sources.open_library.get_with_retry",
        lambda *a, **k: FakeResponse({
            "ISBN:9781632368287": {
                "title": "Attack on Titan. 29",
                "authors": [{"name": "Hajime Isayama"}],
                "publishers": [{"name": "Kodansha Comics"}],
                "publish_date": "2019",
                "cover": {"large": "https://covers.openlibrary.org/b/id/9255173-L.jpg"},
            }
        }),
    )
    source = OpenLibrarySource()
    result = source.lookup_isbn("9781632368287")
    assert result["title"] == "Attack on Titan. 29"
    assert result["author"] == "Hajime Isayama"
    assert result["publisher"] == "Kodansha Comics"
    assert result["year"] == 2019
    assert result["_image_url"] == "https://covers.openlibrary.org/b/id/9255173-L.jpg"


def test_lookup_isbn_joins_multiple_authors(monkeypatch):
    monkeypatch.setattr(
        "library.metadata_sources.open_library.get_with_retry",
        lambda *a, **k: FakeResponse({
            "ISBN:0000000000001": {"authors": [{"name": "A Writer"}, {"name": "B Artist"}]}
        }),
    )
    source = OpenLibrarySource()
    assert source.lookup_isbn("0000000000001")["author"] == "A Writer, B Artist"


def test_lookup_isbn_returns_empty_dict_when_not_found(monkeypatch):
    monkeypatch.setattr(
        "library.metadata_sources.open_library.get_with_retry",
        lambda *a, **k: FakeResponse({}),
    )
    source = OpenLibrarySource()
    assert source.lookup_isbn("0000000000000") == {}
