"""Mirrors data/library_comics.json to a live Google Sheet.

Full-overwrite sync only: every sync_comics_to_sheet call clears the
target worksheet and rewrites it from the current library contents.
Deliberately not incremental — see
docs/superpowers/specs/2026-09-07-google-sheets-sync-design.md.
"""
from __future__ import annotations

from pathlib import Path

import gspread
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from library.config import Config
from library.models import ComicRecord

_HEADER = ["Title", "Series", "Issue #", "Author", "Year", "Publisher", "Status", "Formats", "Added Date"]


def _comic_to_row(record: ComicRecord) -> list[str]:
    if record.series and record.issue_number:
        title = f"{record.series} #{record.issue_number}"
    else:
        title = record.title
    return [
        title,
        record.series or "",
        record.issue_number or "",
        record.author or "",
        str(record.year) if record.year else "",
        record.publisher or "",
        record.status,
        ", ".join(record.formats),
        record.added_date,
    ]


_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _authorize(config: Config) -> gspread.Client:
    """Loads a cached OAuth token, refreshing or running the interactive
    consent flow as needed, and returns an authorized gspread client."""
    token_path = Path(config.google_sheets.token_path)
    client_secret_path = Path(config.google_sheets.client_secret_path)

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), _SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
        token_path.chmod(0o600)
    return gspread.authorize(creds)


def sync_comics_to_sheet(records: dict[str, ComicRecord], config: Config) -> None:
    """Clears the configured worksheet and rewrites it from `records` —
    a full mirror, not an incremental update. See module docstring."""
    client = _authorize(config)
    sheet = client.open_by_key(config.google_sheets.spreadsheet_id)
    worksheet = sheet.worksheet(config.google_sheets.worksheet_name)

    ordered = sorted(records.values(), key=lambda r: (r.added_date, r.id), reverse=True)
    rows = [_HEADER] + [_comic_to_row(r) for r in ordered]

    worksheet.clear()
    worksheet.update(rows)
