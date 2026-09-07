from pathlib import Path

import yaml
from click.testing import CliRunner

from cli import main


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump({"roots": [{"path": str(tmp_path), "type": "comic"}]}))
    return config_path


_FETCHED_INFO = {
    "series": "Absolute Batman", "issue_number": "16", "publisher": "DC Comics", "year": 2026,
    "description": "A synopsis.", "author": "Scott Snyder", "upc": "76194138584601611",
    "_image_url": "https://s3.amazonaws.com/comicgeeks/comics/covers/large-6297209.jpg",
}


class FakeCoverResponse:
    content = b"fake-cover-bytes"

    def raise_for_status(self):
        pass


def test_add_comic_rejects_non_comic_geeks_url(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["add-comic", "https://metron.cloud/issue/absolute-batman-2024-16/", "--config", str(config_path)])

    assert result.exit_code != 0
    assert "leagueofcomicgeeks.com" in result.output


def test_add_comic_reports_unreadable_page(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: {})

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)])

    assert result.exit_code != 0
    assert "Couldn't read" in result.output


def test_add_comic_creates_new_digital_record_by_default(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)])

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert "upc-76194138584601611" in library
    assert '"digital"' in library


def test_add_comic_physical_flag_adds_print_format(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--physical", "--config", str(config_path)])

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert '"print"' in library
    assert '"digital"' not in library


def test_add_comic_adds_format_to_already_existing_record(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "library_comics.json").write_text(
        '[{"id": "upc-76194138584601611", "title": "Absolute Batman #16", "type": "comic", '
        '"series": "Absolute Batman", "issue_number": "16", "formats": ["print"], "metadata_source": {}, '
        '"preview_pages": [], "status": "unread", "added_date": "2026-01-01"}]'
    )
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)])

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert library.count('"id": "upc-76194138584601611"') == 1  # not duplicated
    assert '"digital"' in library
    assert '"print"' in library


def test_add_comic_merges_into_record_with_different_id_via_series_and_issue(tmp_path: Path, monkeypatch):
    """A digital scan has its own content-hash id, unrelated to the UPC a
    Comic Geeks link resolves to — the merge has to go by series+issue,
    not by id, or this would wrongly create a duplicate physical record."""
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    data_dir.joinpath("library_comics.json").write_text(
        '[{"id": "abcd1234-scanned", "title": "Absolute Batman #16", "type": "comic", '
        '"series": "Absolute Batman", "issue_number": "16", "formats": ["digital"], "metadata_source": {}, '
        '"preview_pages": [], "status": "unread", "added_date": "2026-01-01"}]'
    )
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--physical", "--config", str(config_path)])

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert library.count('"id":') == 1  # merged, not duplicated
    assert '"abcd1234-scanned"' in library
    assert "upc-76194138584601611" not in library
    assert '"digital"' in library and '"print"' in library
