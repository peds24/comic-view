from datetime import date
from pathlib import Path

import yaml
from click.testing import CliRunner

from cli import main
from library.pull_calendar import PulledItem


def _write_config(tmp_path: Path, calendar_url: str = "https://leagueofcomicgeeks.com/member/calendar_ics/peds24") -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump({
        "roots": [{"path": str(tmp_path), "type": "comic"}],
        "metron": {"username": "user", "password": "pass"},
        "pull_list": {"calendar_url": calendar_url},
    }))
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

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "Added 1" in result.output
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert "metron-999" in library
    state = (tmp_path / "data" / "pull_state.json").read_text()
    assert "uid@cg" in state


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
