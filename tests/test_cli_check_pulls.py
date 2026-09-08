from datetime import date
from pathlib import Path

import yaml
from click.testing import CliRunner

from cli import main
from library.pull_calendar import PulledItem


def _write_config(tmp_path: Path, calendar_url: str = "https://leagueofcomicgeeks.com/member/calendar_ics/peds24", google_sheets: dict | None = None) -> Path:
    config_path = tmp_path / "config.yaml"
    data = {
        "roots": [{"path": str(tmp_path), "type": "comic"}],
        "metron": {"username": "user", "password": "pass"},
        "pull_list": {"calendar_url": calendar_url},
    }
    if google_sheets:
        data["google_sheets"] = google_sheets
    config_path.write_text(yaml.dump(data))
    return config_path


def test_check_pulls_reports_no_configured_calendar(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path, calendar_url="")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert "No pull_list.calendar_url configured" in result.output


def test_check_pulls_adds_new_confident_match_and_updates_state(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    item = PulledItem(event_uid="uid@cg", release_date=date(2020, 1, 1), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: ({"id": 999, "series": {"name": "Batman"}, "number": "13"}, "ok", []),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert "Added 1" in result.output
    assert "Batman #13" in result.output  # confirmation preview
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert "metron-999" in library
    state = (tmp_path / "data" / "pull_state.json").read_text()
    assert "uid@cg" in state


def test_check_pulls_declining_confirmation_makes_no_changes(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    item = PulledItem(event_uid="uid@cg", release_date=date(2020, 1, 1), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: ({"id": 999, "series": {"name": "Batman"}, "number": "13"}, "ok", []),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)], input="n\n")

    assert result.exit_code == 0
    assert "Cancelled" in result.output
    assert not (tmp_path / "data" / "library_comics.json").exists()
    assert not (tmp_path / "data" / "pull_state.json").exists()


def test_check_pulls_skips_already_processed_events(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "pull_state.json").write_text('{"processed_uids": ["uid@cg"]}')

    item = PulledItem(event_uid="uid@cg", release_date=date(2026, 10, 7), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: (_ for _ in ()).throw(AssertionError("should not resolve an already-processed item")),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "0 new" in result.output


def test_check_pulls_skips_future_releases(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    far_future = date(2099, 1, 1)
    item = PulledItem(event_uid="uid@cg", release_date=far_future, title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: (_ for _ in ()).throw(AssertionError("should not resolve a not-yet-released item")),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "0 new" in result.output


def test_check_pulls_reports_flagged_items(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    item = PulledItem(event_uid="uid@cg", release_date=date(2020, 1, 1), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: (None, "ambiguous", [{"series_id": 1, "series_name": "Batman (1940)", "publisher": "DC", "year_began": 1940, "year_end": 2011}]),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "FLAGGED: Batman #13" in result.output


def test_check_pulls_flagged_item_is_still_marked_processed(tmp_path: Path, monkeypatch):
    """A flagged item's UID must still land in pull_state.json, or the
    weekly routine would re-flag the same item forever."""
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    item = PulledItem(event_uid="uid@cg", release_date=date(2020, 1, 1), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: (None, "not_found", []),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert result.exit_code == 0
    state = (tmp_path / "data" / "pull_state.json").read_text()
    assert "uid@cg" in state


def test_check_pulls_handles_metron_exception_without_crashing(tmp_path: Path, monkeypatch):
    """A single HTTP failure partway through a run must not crash the
    whole command — earlier/later items' work in the same run still needs
    to be saved (see resolve_and_add's own defensive-Metron-call pattern
    in physical_importer.py)."""
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    good_item = PulledItem(event_uid="good@cg", release_date=date(2020, 1, 1), title="Batman #13", price="$4.99")
    bad_item = PulledItem(event_uid="bad@cg", release_date=date(2020, 1, 1), title="Detective Comics #27", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [good_item, bad_item])

    def _find_issue_confident(self, series, number, year=None):
        if series == "Detective Comics":
            raise ConnectionError("boom")
        return ({"id": 999, "series": {"name": "Batman"}, "number": "13"}, "ok", [])

    monkeypatch.setattr("cli.MetronSource.find_issue_confident", _find_issue_confident)

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert "Added 1" in result.output
    assert "flagged 1" in result.output
    assert "FLAGGED: Detective Comics #27" in result.output
    assert "lookup failed" in result.output

    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert "metron-999" in library  # good item's work was saved despite the later failure

    state = (tmp_path / "data" / "pull_state.json").read_text()
    assert "good@cg" in state
    assert "bad@cg" in state  # flagged item's UID still recorded so it isn't retried forever


_SHEETS_CONFIG = {
    "spreadsheet_id": "abc123",
    "worksheet_name": "Comics",
    "client_secret_path": "secrets/google_client_secret.json",
    "token_path": "secrets/google_token.json",
}


def test_check_pulls_syncs_to_sheets_when_configured(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path, google_sheets=_SHEETS_CONFIG)
    monkeypatch.chdir(tmp_path)

    item = PulledItem(event_uid="uid@cg", release_date=date(2020, 1, 1), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: ({"id": 999, "series": {"name": "Batman"}, "number": "13"}, "ok", []),
    )
    synced_with = []
    monkeypatch.setattr("cli.sync_comics_to_sheet", lambda records, config: synced_with.append(records))

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert "Synced to Google Sheets." in result.output
    assert len(synced_with) == 1
    assert "metron-999" in synced_with[0]


def test_check_pulls_reports_sheets_sync_failure_as_warning(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path, google_sheets=_SHEETS_CONFIG)
    monkeypatch.chdir(tmp_path)

    item = PulledItem(event_uid="uid@cg", release_date=date(2020, 1, 1), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: ({"id": 999, "series": {"name": "Batman"}, "number": "13"}, "ok", []),
    )

    def _boom(records, config):
        raise RuntimeError("network down")
    monkeypatch.setattr("cli.sync_comics_to_sheet", _boom)

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert "Warning: could not sync to Google Sheets: network down" in result.output
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert "metron-999" in library  # local library still updated despite sync failure


def test_check_pulls_skips_sync_when_not_configured(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)  # no google_sheets block
    monkeypatch.chdir(tmp_path)

    item = PulledItem(event_uid="uid@cg", release_date=date(2020, 1, 1), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: ({"id": 999, "series": {"name": "Batman"}, "number": "13"}, "ok", []),
    )

    def _fail_if_called(records, config):
        raise AssertionError("sync_comics_to_sheet should not be called when not configured")
    monkeypatch.setattr("cli.sync_comics_to_sheet", _fail_if_called)

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert "Synced to Google Sheets." not in result.output
