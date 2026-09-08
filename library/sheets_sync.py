"""Mirrors data/library_comics.json to a live Google Sheet.

Incremental upsert: sync_comics_to_sheet reads the sheet's current rows,
updates in place only the rows whose content actually changed, and inserts
brand-new comics as new rows at the top (newest `added_date` first) —
it never clears or rewrites rows that don't need to change. See
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

# Matches the live sheet's "Comics" table.
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


def _insert_new_rows_at_top(sheet: gspread.Spreadsheet, worksheet: gspread.Worksheet, rows: list[list[str]]) -> None:
    """Shifts existing data rows down and writes `rows` into the freshly
    opened space starting at row 2, so newly added comics keep landing at
    the top (newest first) without touching any existing row."""
    sheet.batch_update({
        "requests": [{
            "insertDimension": {
                "range": {
                    "sheetId": worksheet.id,
                    "dimension": "ROWS",
                    "startIndex": 1,
                    "endIndex": 1 + len(rows),
                },
                "inheritFromBefore": False,
            }
        }]
    })
    worksheet.update(rows, "A2", raw=False)


def sync_comics_to_sheet(records: dict[str, ComicRecord], config: Config) -> None:
    """Upserts `records` into the configured worksheet: a comic already
    present (matched by its Title cell) has its row updated in place only
    if the content actually changed; a comic not yet in the sheet is
    inserted as a new row at the top (newest `added_date` first). Existing
    rows that don't need to change are left completely alone — this never
    clears or regenerates the sheet, so manual formatting/columns/Table
    setup on the sheet survive every sync. See module docstring."""
    client = _authorize(config)
    sheet = client.open_by_key(config.google_sheets.spreadsheet_id)
    worksheet = sheet.worksheet(config.google_sheets.worksheet_name)

    existing_values = worksheet.get_all_values()

    if not existing_values:
        ordered = sorted(records.values(), key=lambda r: (r.added_date, r.id), reverse=True)
        rows = [_HEADER] + [_comic_to_row(r) for r in ordered]
        worksheet.update(rows, raw=False)
        _resize_table_to_fit(sheet, worksheet, len(rows))
        return

    existing_rows = existing_values[1:]
    title_to_row_index = {row[0]: i for i, row in enumerate(existing_rows) if row}

    new_records = []
    for record in records.values():
        row = _comic_to_row(record)
        idx = title_to_row_index.get(row[0])
        if idx is None:
            new_records.append(record)
        elif existing_rows[idx] != row:
            worksheet.update([row], f"A{idx + 2}", raw=False)

    if new_records:
        new_records.sort(key=lambda r: (r.added_date, r.id), reverse=True)
        _insert_new_rows_at_top(sheet, worksheet, [_comic_to_row(r) for r in new_records])

    _resize_table_to_fit(sheet, worksheet, len(existing_values) + len(new_records))
