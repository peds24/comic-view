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

# Matches the live sheet's "Comics" table, which the user converted to a
# native Sheets Table and extended with a "Helper" column (a formula, not
# library data — see _HELPER_FORMULA below).
_HEADER = ["Title", "Helper", "Series", "Issue #", "Author", "Year", "Publisher", "Status", "Formats", "Added Date"]

# The user added this to every row so a QUERY/sort elsewhere on the sheet
# can pull out the issue number as a real number. It references the row's
# own Title cell, so re-templating it per row on every full-overwrite sync
# keeps it correct even though rows get resorted (new comics land on top).
_HELPER_FORMULA = '=VALUE(REGEXEXTRACT(A{row}, "#(\\d+)"))'


def _comic_to_row(record: ComicRecord, sheet_row: int) -> list[str]:
    if record.series and record.issue_number:
        title = f"{record.series} #{record.issue_number}"
    else:
        title = record.title
    return [
        title,
        _HELPER_FORMULA.format(row=sheet_row),
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


def _resize_table_to_fit(sheet: gspread.Spreadsheet, worksheet: gspread.Worksheet, total_rows: int) -> None:
    """Extends the worksheet's native Table (if the user has converted it to
    one) to cover every row just written, so newly added comics land inside
    the table's banding/dropdowns/filters instead of as plain rows below it.
    No-ops if the worksheet isn't a Table."""
    metadata = sheet.fetch_sheet_metadata(params={"fields": "sheets(properties.sheetId,tables)"})
    for sheet_props in metadata.get("sheets", []):
        if sheet_props["properties"]["sheetId"] != worksheet.id:
            continue
        for table in sheet_props.get("tables", []):
            table_range = table["range"]
            if table_range["endRowIndex"] == total_rows:
                continue
            sheet.batch_update({
                "requests": [{
                    "updateTable": {
                        "table": {
                            "tableId": table["tableId"],
                            "range": {**table_range, "sheetId": worksheet.id, "endRowIndex": total_rows},
                        },
                        "fields": "range",
                    }
                }]
            })


def sync_comics_to_sheet(records: dict[str, ComicRecord], config: Config) -> None:
    """Clears the configured worksheet and rewrites it from `records` —
    a full mirror, not an incremental update. See module docstring."""
    client = _authorize(config)
    sheet = client.open_by_key(config.google_sheets.spreadsheet_id)
    worksheet = sheet.worksheet(config.google_sheets.worksheet_name)

    ordered = sorted(records.values(), key=lambda r: (r.added_date, r.id), reverse=True)
    rows = [_HEADER] + [_comic_to_row(r, sheet_row=i + 2) for i, r in enumerate(ordered)]

    worksheet.clear()
    worksheet.update(rows, raw=False)
    _resize_table_to_fit(sheet, worksheet, len(rows))
