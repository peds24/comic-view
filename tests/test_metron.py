from pathlib import Path

from library.metadata_sources.metron import MetronSource, apply_metron_issue, year_from_issue
from library.models import ComicRecord


class FakeResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_extract_writer_collects_all_writers_deduped():
    issue = {
        "credits": [
            {"creator": "Jeph Loeb", "role": [{"name": "Writer"}]},
            {"creator": "Tim Sale", "role": [{"name": "Penciller"}, {"name": "Cover"}]},
            {"creator": "Grant Morrison", "role": [{"name": "Writer"}]},
            {"creator": "Jeph Loeb", "role": [{"name": "Writer"}]},  # duplicate credit row
        ]
    }
    assert MetronSource._extract_writer(issue) == "Jeph Loeb, Grant Morrison"


def test_extract_writer_returns_none_when_no_writer_credited():
    assert MetronSource._extract_writer({"credits": [{"creator": "Tim Sale", "role": [{"name": "Cover"}]}]}) is None


def test_find_issue_by_upc_returns_issue_detail(monkeypatch):
    calls = []

    def fake_get(url, params=None, auth=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/issue/"):
            assert params == {"upc": "76194138584601011"}
            return FakeResponse({"results": [{"id": 149272}]})
        assert url.endswith("/issue/149272/")
        return FakeResponse({"id": 149272, "desc": "Bruce Wayne trapped.", "image": "https://example.com/cover.jpg"})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue = source.find_issue_by_upc("76194138584601011")

    assert issue["id"] == 149272
    assert issue["image"] == "https://example.com/cover.jpg"
    assert len(calls) == 2


def test_find_issue_by_upc_returns_none_when_no_match(monkeypatch):
    monkeypatch.setattr(
        "library.http_utils.requests.get",
        lambda *a, **k: FakeResponse({"results": []}),
    )
    source = MetronSource("user", "pass")
    assert source.find_issue_by_upc("0000000000000") is None


def test_find_issue_by_series_and_number(monkeypatch):
    calls = []

    def fake_get(url, params=None, auth=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/series/"):
            assert params == {"name": "Absolute Batman"}
            return FakeResponse({"results": [{"id": 8477, "series": "Absolute Batman (2024)", "year_began": 2024}]})
        if url.endswith("/issue/"):
            assert params == {"series_id": 8477, "number": "14"}
            return FakeResponse({"results": [{"id": 156811}]})
        assert url.endswith("/issue/156811/")
        return FakeResponse({"id": 156811, "number": "14", "image": "https://example.com/14.jpg"})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue = source.find_issue_by_series_and_number("Absolute Batman", "14")

    assert issue["id"] == 156811
    assert issue["image"] == "https://example.com/14.jpg"
    assert len(calls) == 3


def test_find_series_disambiguates_same_name_series_by_year(monkeypatch):
    """Regression test: Metron's `name` filter is substring/relevance search
    (e.g. plain "Batman" returns "Absolute Batman" as the top hit among 446
    matches) and a name can legitimately be reused across eras (four
    different "Batman" series: 1940, 2011, 2016, 2025) — picking
    results[0] silently attached the wrong series' issues/covers."""
    series_page = {
        "results": [
            {"id": 8477, "series": "Absolute Batman (2024)", "year_began": 2024},  # top relevance hit, wrong
            {"id": 2481, "series": "Batman (1940)", "year_began": 1940, "year_end": 2011},
            {"id": 763, "series": "Batman (2011)", "year_began": 2011, "year_end": 2016},
            {"id": 93, "series": "Batman (2016)", "year_began": 2016, "year_end": 2024},
            {"id": 12829, "series": "Batman (2025)", "year_began": 2025, "year_end": None},
        ]
    }

    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/series/"):
            assert params == {"name": "Batman"}
            return FakeResponse(series_page)
        if url.endswith("/issue/"):
            assert params == {"series_id": 12829, "number": "1"}
            return FakeResponse({"results": [{"id": 999}]})
        return FakeResponse({"id": 999, "image": "https://example.com/batman-2025-1.jpg"})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue = source.find_issue_by_series_and_number("Batman", "1", year=2025)

    assert issue["id"] == 999


def test_find_issue_by_series_and_number_returns_none_when_series_not_found(monkeypatch):
    monkeypatch.setattr(
        "library.http_utils.requests.get",
        lambda *a, **k: FakeResponse({"results": []}),
    )
    source = MetronSource("user", "pass")
    assert source.find_issue_by_series_and_number("Nonexistent Series", "1") is None


def test_year_from_issue_uses_store_date_not_cover_date():
    """Store date (when the issue actually shipped) is used instead of
    cover date (a nominal, often several-months-later publisher
    convention)."""
    issue = {"cover_date": "2025-09-01", "store_date": "2025-07-16"}
    assert year_from_issue(issue) == 2025


def test_year_from_issue_returns_none_when_missing():
    assert year_from_issue({}) is None
    assert year_from_issue({"store_date": None}) is None


def test_find_issue_confident_ok_when_only_one_series_has_the_issue(monkeypatch):
    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/series/"):
            assert params == {"name": "Batman"}
            return FakeResponse({"results": [
                {"id": 2481, "series": "Batman (1940)", "year_began": 1940, "year_end": 2011},
                {"id": 12829, "series": "Batman (2025)", "year_began": 2025, "year_end": None},
            ]})
        if url.endswith("/issue/") and params.get("series_id") == 2481:
            return FakeResponse({"results": []})
        if url.endswith("/issue/") and params.get("series_id") == 12829:
            return FakeResponse({"results": [{"id": 999}]})
        assert url.endswith("/issue/999/")
        return FakeResponse({"id": 999, "number": "13"})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Batman", "13")

    assert status == "ok"
    assert issue["id"] == 999
    assert candidates == []


def test_find_issue_confident_ambiguous_when_two_series_both_have_the_issue(monkeypatch):
    """Regression test for the reported real failure: an ended 'Batman'
    run and the current 'Batman (2025)' relaunch both existing only
    matters if both also happen to have reached the same issue number —
    here they both have a #13, so neither should be silently chosen."""
    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/series/"):
            return FakeResponse({"results": [
                {"id": 2481, "series": "Batman (1940)", "year_began": 1940, "year_end": 2011,
                 "publisher": {"name": "DC Comics"}},
                {"id": 12829, "series": "Batman (2025)", "year_began": 2025, "year_end": None,
                 "publisher": {"name": "DC Comics"}},
            ]})
        assert url.endswith("/issue/")
        return FakeResponse({"results": [{"id": params["series_id"] * 10}]})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Batman", "13")

    assert status == "ambiguous"
    assert issue is None
    assert {c["series_id"] for c in candidates} == {2481, 12829}
    assert all(c["publisher"] == "DC Comics" for c in candidates)


def test_find_issue_confident_uses_year_to_break_ambiguity(monkeypatch):
    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/series/"):
            return FakeResponse({"results": [
                {"id": 2481, "series": "Batman (1940)", "year_began": 1940, "year_end": 2011},
                {"id": 12829, "series": "Batman (2025)", "year_began": 2025, "year_end": None},
            ]})
        if url.endswith("/issue/") and params.get("series_id") == 2481:
            return FakeResponse({"results": [{"id": 111}]})
        if url.endswith("/issue/") and params.get("series_id") == 12829:
            return FakeResponse({"results": [{"id": 999}]})
        assert url.endswith("/issue/999/")
        return FakeResponse({"id": 999, "number": "13"})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Batman", "13", year=2026)

    assert status == "ok"
    assert issue["id"] == 999


def test_find_issue_confident_not_found_when_no_series_has_the_issue(monkeypatch):
    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/series/"):
            return FakeResponse({"results": [{"id": 12829, "series": "Batman (2025)", "year_began": 2025}]})
        return FakeResponse({"results": []})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Batman", "999")

    assert status == "not_found"
    assert issue is None
    assert candidates == []


def test_find_issue_confident_not_found_when_series_name_unknown(monkeypatch):
    monkeypatch.setattr("library.http_utils.requests.get", lambda *a, **k: FakeResponse({"results": []}))
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Nonexistent Series", "1")

    assert status == "not_found"


def test_apply_metron_issue_fills_empty_fields_and_downloads_cover(tmp_path: Path, monkeypatch):
    class FakeCoverResponse:
        content = b"fake-cover-bytes"

        def raise_for_status(self):
            pass

    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    record = ComicRecord(id="metron-999", title="Batman #13", type="comic", formats=["print"])
    issue = {
        "id": 999,
        "series": {"name": "Batman"},
        "number": "13",
        "publisher": {"name": "DC Comics"},
        "store_date": "2026-10-07",
        "desc": "A synopsis.",
        "credits": [{"creator": "Chip Zdarsky", "role": [{"name": "Writer"}]}],
        "image": "https://example.com/batman-13.jpg",
    }

    apply_metron_issue(record, issue, tmp_path)

    assert record.series == "Batman"
    assert record.issue_number == "13"
    assert record.publisher == "DC Comics"
    assert record.year == 2026
    assert record.description == "A synopsis."
    assert record.author == "Chip Zdarsky"
    assert record.metadata_source["series"] == "metron"
    assert record.cover_path == "metron-999/cover.jpg"


def test_apply_metron_issue_does_not_overwrite_existing_fields(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fetch a cover")))

    record = ComicRecord(id="metron-999", title="Batman #13", type="comic", formats=["print"], publisher="Already Set")
    apply_metron_issue(record, {"id": 999, "publisher": {"name": "DC Comics"}}, tmp_path)

    assert record.publisher == "Already Set"


