from pathlib import Path

import yaml

from library.config import load_config


def _write_config(tmp_path: Path, extra: dict | None = None) -> Path:
    config_path = tmp_path / "config.yaml"
    data = {"roots": [{"path": str(tmp_path), "type": "comic"}]}
    if extra:
        data.update(extra)
    config_path.write_text(yaml.dump(data))
    return config_path


def test_google_sheets_defaults_to_not_configured(tmp_path: Path):
    config_path = _write_config(tmp_path)

    config = load_config(config_path)

    assert config.google_sheets.is_configured is False
    assert config.google_sheets.worksheet_name == "Comics"
    assert config.google_sheets.client_secret_path == "secrets/google_client_secret.json"
    assert config.google_sheets.token_path == "secrets/google_token.json"


def test_google_sheets_configured_when_spreadsheet_id_set(tmp_path: Path):
    config_path = _write_config(tmp_path, {
        "google_sheets": {
            "spreadsheet_id": "abc123",
            "worksheet_name": "MyTab",
            "client_secret_path": "secrets/custom_secret.json",
            "token_path": "secrets/custom_token.json",
        }
    })

    config = load_config(config_path)

    assert config.google_sheets.is_configured is True
    assert config.google_sheets.spreadsheet_id == "abc123"
    assert config.google_sheets.worksheet_name == "MyTab"
    assert config.google_sheets.client_secret_path == "secrets/custom_secret.json"
    assert config.google_sheets.token_path == "secrets/custom_token.json"
