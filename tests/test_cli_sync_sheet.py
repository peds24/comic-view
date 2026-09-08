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


def test_sync_sheet_reports_not_configured(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["sync-sheet", "--config", str(config_path)])

    assert result.exit_code != 0
    assert "google_sheets not configured" in result.output


def test_sync_sheet_syncs_library_when_configured(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path, google_sheets={
        "spreadsheet_id": "abc123",
        "worksheet_name": "Comics",
        "client_secret_path": "secrets/google_client_secret.json",
        "token_path": "secrets/google_token.json",
    })
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "library_comics.json").write_text(
        '[{"id": "a", "title": "Batman #1", "type": "comic", "formats": ["digital"], '
        '"metadata_source": {}, "preview_pages": [], "status": "unread", "added_date": "2026-01-01"}]'
    )
    synced_with = []
    monkeypatch.setattr("cli.sync_comics_to_sheet", lambda records, config: synced_with.append(records))

    result = CliRunner().invoke(main, ["sync-sheet", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "Synced 1 comic(s)" in result.output
    assert "a" in synced_with[0]
