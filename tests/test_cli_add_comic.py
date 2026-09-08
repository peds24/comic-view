from pathlib import Path

import yaml
from click.testing import CliRunner

from cli import main


def _write_config(tmp_path: Path, google_sheets: dict | None = None) -> Path:
    config_path = tmp_path / "config.yaml"
    data = {"roots": [{"path": str(tmp_path), "type": "comic"}]}
    if google_sheets:
        data["google_sheets"] = google_sheets
    config_path.write_text(yaml.dump(data))
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

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert "A synopsis." in result.output  # confirmation preview shows the fetched description
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert "upc-76194138584601611" in library
    assert '"digital"' in library


def test_add_comic_physical_flag_adds_print_format(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--physical", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert '"print"' in library
    assert '"digital"' not in library


def test_add_comic_declining_confirmation_makes_no_changes(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)], input="n\n")

    assert result.exit_code == 0
    assert "Cancelled" in result.output
    assert not (tmp_path / "data" / "library_comics.json").exists()


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

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert library.count('"id": "upc-76194138584601611"') == 1  # not duplicated
    assert '"digital"' in library
    assert '"print"' in library


def test_add_comic_falls_back_to_cgeeks_id_when_no_upc(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    info_without_upc = {k: v for k, v in _FETCHED_INFO.items() if k != "upc"}
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(info_without_upc))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert '"id": "cgeeks-6297209"' in library


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

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--physical", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert library.count('"id":') == 1  # merged, not duplicated
    assert '"abcd1234-scanned"' in library
    assert "upc-76194138584601611" not in library
    assert '"digital"' in library and '"print"' in library


_SHEETS_CONFIG = {
    "spreadsheet_id": "abc123",
    "worksheet_name": "Comics",
    "client_secret_path": "secrets/google_client_secret.json",
    "token_path": "secrets/google_token.json",
}


def test_add_comic_syncs_new_record_to_sheets_when_configured(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path, google_sheets=_SHEETS_CONFIG)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())
    synced_with = []
    monkeypatch.setattr("cli.sync_comics_to_sheet", lambda records, config: synced_with.append(records))

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert len(synced_with) == 1


def test_add_comic_syncs_merged_record_to_sheets_when_configured(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path, google_sheets=_SHEETS_CONFIG)
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
    synced_with = []
    monkeypatch.setattr("cli.sync_comics_to_sheet", lambda records, config: synced_with.append(records))

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert len(synced_with) == 1


def test_add_comic_reports_sheets_sync_failure_as_warning(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path, google_sheets=_SHEETS_CONFIG)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    def _boom(records, config):
        raise RuntimeError("network down")
    monkeypatch.setattr("cli.sync_comics_to_sheet", _boom)

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert "Warning: could not sync to Google Sheets: network down" in result.output
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert "Absolute Batman" in library  # local library still updated despite sync failure


def test_add_comic_skips_sync_when_not_configured(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)  # no google_sheets block
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())
    calls = []
    monkeypatch.setattr("cli.sync_comics_to_sheet", lambda records, config: calls.append(records))

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert calls == []
    assert "Google Sheets" not in result.output
