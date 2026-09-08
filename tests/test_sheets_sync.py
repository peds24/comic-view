from library.models import ComicRecord
from library.sheets_sync import _HEADER, _comic_to_row


def _record(**overrides) -> ComicRecord:
    defaults = dict(
        id="cgeeks-1",
        title="Absolute Batman #16",
        type="comic",
        series="Absolute Batman",
        issue_number="16",
        author="Scott Snyder",
        year=2026,
        publisher="DC Comics",
        status="unread",
        formats=["digital"],
        added_date="2026-09-07",
    )
    defaults.update(overrides)
    return ComicRecord(**defaults)


def test_header_matches_row_length():
    assert len(_HEADER) == len(_comic_to_row(_record(), sheet_row=2))


def test_comic_to_row_uses_series_and_issue_for_title():
    row = _comic_to_row(_record(), sheet_row=2)
    assert row == [
        "Absolute Batman #16", '=VALUE(REGEXEXTRACT(A2, "#(\\d+)"))', "Absolute Batman", "16",
        "Scott Snyder", "2026", "DC Comics", "unread", "digital", "2026-09-07",
    ]


def test_comic_to_row_helper_formula_references_own_row():
    row = _comic_to_row(_record(), sheet_row=48)
    assert row[1] == '=VALUE(REGEXEXTRACT(A48, "#(\\d+)"))'


def test_comic_to_row_falls_back_to_title_without_series_or_issue():
    record = _record(title="Some One-Shot", series=None, issue_number=None)
    row = _comic_to_row(record, sheet_row=2)
    assert row[0] == "Some One-Shot"
    assert row[2] == ""
    assert row[3] == ""


def test_comic_to_row_blanks_missing_optional_fields():
    record = _record(author=None, year=None, publisher=None)
    row = _comic_to_row(record, sheet_row=2)
    assert row[4] == ""  # author
    assert row[5] == ""  # year
    assert row[6] == ""  # publisher


def test_comic_to_row_joins_multiple_formats():
    record = _record(formats=["digital", "print"])
    row = _comic_to_row(record, sheet_row=2)
    assert row[8] == "digital, print"


from library.config import Config, GoogleSheetsConfig, MetronConfig, GoogleBooksConfig, PullListConfig
from library.sheets_sync import sync_comics_to_sheet, _authorize


class _FakeWorksheet:
    def __init__(self, sheet_id=0):
        self.id = sheet_id
        self.cleared = False
        self.updated_with = None
        self.update_kwargs = None

    def clear(self):
        self.cleared = True

    def update(self, rows, **kwargs):
        self.updated_with = rows
        self.update_kwargs = kwargs


class _FakeSheet:
    def __init__(self, worksheet, tables=None):
        self._worksheet = worksheet
        self._tables = tables or []
        self.batch_update_calls = []

    def worksheet(self, name):
        self._requested_name = name
        return self._worksheet

    def fetch_sheet_metadata(self, params=None):
        return {
            "sheets": [
                {
                    "properties": {"sheetId": self._worksheet.id},
                    "tables": self._tables,
                }
            ]
        }

    def batch_update(self, body):
        self.batch_update_calls.append(body)


class _FakeClient:
    def __init__(self, sheet):
        self._sheet = sheet

    def open_by_key(self, key):
        self._requested_key = key
        return self._sheet


def _config(**sheets_overrides) -> Config:
    sheets = GoogleSheetsConfig(
        spreadsheet_id="abc123",
        worksheet_name="Comics",
        client_secret_path="secrets/google_client_secret.json",
        token_path="secrets/google_token.json",
    )
    for key, value in sheets_overrides.items():
        setattr(sheets, key, value)
    return Config(
        roots=[],
        metron=MetronConfig(),
        google_books=GoogleBooksConfig(),
        data_dir=".",
        pull_list=PullListConfig(),
        google_sheets=sheets,
    )


def test_sync_comics_to_sheet_clears_and_writes_header_plus_rows(monkeypatch):
    worksheet = _FakeWorksheet()
    client = _FakeClient(_FakeSheet(worksheet))
    monkeypatch.setattr("library.sheets_sync._authorize", lambda config: client)

    older = _record(id="a", added_date="2026-01-01", series="Older", issue_number="1")
    newer = _record(id="b", added_date="2026-09-01", series="Newer", issue_number="2")
    records = {"a": older, "b": newer}

    sync_comics_to_sheet(records, _config())

    assert worksheet.cleared is True
    assert worksheet.updated_with[0] == _HEADER
    assert worksheet.updated_with[1][2] == "Newer"  # sorted by added_date descending
    assert worksheet.updated_with[2][2] == "Older"
    assert worksheet.updated_with[1][1] == '=VALUE(REGEXEXTRACT(A2, "#(\\d+)"))'
    assert worksheet.updated_with[2][1] == '=VALUE(REGEXEXTRACT(A3, "#(\\d+)"))'
    assert worksheet.update_kwargs == {"raw": False}  # formulas must be parsed, not stored as literal text
    assert client._requested_key == "abc123"
    assert client._sheet._requested_name == "Comics"


def test_sync_comics_to_sheet_resizes_native_table_to_fit_row_count(monkeypatch):
    worksheet = _FakeWorksheet(sheet_id=42)
    existing_table = {
        "tableId": "T1",
        "range": {"startRowIndex": 0, "endRowIndex": 3, "startColumnIndex": 0, "endColumnIndex": 10},
    }
    fake_sheet = _FakeSheet(worksheet, tables=[existing_table])
    client = _FakeClient(fake_sheet)
    monkeypatch.setattr("library.sheets_sync._authorize", lambda config: client)

    records = {"a": _record(id="a"), "b": _record(id="b"), "c": _record(id="c")}
    sync_comics_to_sheet(records, _config())

    assert len(fake_sheet.batch_update_calls) == 1
    request = fake_sheet.batch_update_calls[0]["requests"][0]["updateTable"]
    assert request["table"]["tableId"] == "T1"
    assert request["table"]["range"]["endRowIndex"] == 4  # header + 3 comics
    assert request["table"]["range"]["sheetId"] == 42
    assert request["fields"] == "range"


def test_sync_comics_to_sheet_skips_table_resize_when_already_the_right_size(monkeypatch):
    worksheet = _FakeWorksheet()
    existing_table = {
        "tableId": "T1",
        "range": {"startRowIndex": 0, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 10},
    }
    fake_sheet = _FakeSheet(worksheet, tables=[existing_table])
    client = _FakeClient(fake_sheet)
    monkeypatch.setattr("library.sheets_sync._authorize", lambda config: client)

    sync_comics_to_sheet({"a": _record(id="a")}, _config())

    assert fake_sheet.batch_update_calls == []


def test_sync_comics_to_sheet_skips_table_resize_when_no_table_exists(monkeypatch):
    worksheet = _FakeWorksheet()
    fake_sheet = _FakeSheet(worksheet, tables=[])
    client = _FakeClient(fake_sheet)
    monkeypatch.setattr("library.sheets_sync._authorize", lambda config: client)

    sync_comics_to_sheet({"a": _record(id="a")}, _config())

    assert fake_sheet.batch_update_calls == []


class _FakeExpiredCreds:
    """A cached token that Credentials.from_authorized_user_file would
    return for a token whose refresh_token has been revoked server-side."""

    def __init__(self):
        self.valid = False
        self.expired = True
        self.refresh_token = "some-refresh-token"

    def refresh(self, request):
        from google.auth.exceptions import RefreshError
        raise RefreshError("invalid_grant: Token has been expired or revoked.")


class _FakeFreshCreds:
    """What the interactive consent flow's run_local_server returns."""

    def __init__(self):
        self.valid = True

    def to_json(self):
        return "{}"


class _FakeFlow:
    def __init__(self):
        self.run_local_server_called_with = None

    def run_local_server(self, port):
        self.run_local_server_called_with = port
        return _FakeFreshCreds()


def test_authorize_falls_back_to_interactive_flow_when_refresh_fails(tmp_path, monkeypatch):
    """Reproduces the bug: a stale/revoked cached token whose .refresh()
    raises RefreshError must not propagate — it should fall through to
    the interactive consent flow, per the spec's documented behavior."""
    token_path = tmp_path / "token.json"
    token_path.write_text("{}")  # just needs to exist; from_authorized_user_file is patched below
    client_secret_path = tmp_path / "client_secret.json"
    client_secret_path.write_text("{}")

    monkeypatch.setattr(
        "library.sheets_sync.Credentials.from_authorized_user_file",
        lambda path, scopes: _FakeExpiredCreds(),
    )
    fake_flow = _FakeFlow()
    monkeypatch.setattr(
        "library.sheets_sync.InstalledAppFlow.from_client_secrets_file",
        lambda path, scopes: fake_flow,
    )
    monkeypatch.setattr("library.sheets_sync.gspread.authorize", lambda creds: creds)

    config = _config(token_path=str(token_path), client_secret_path=str(client_secret_path))

    result = _authorize(config)

    assert fake_flow.run_local_server_called_with == 0
    assert result.valid is True
    assert token_path.read_text() == "{}"
    assert (token_path.stat().st_mode & 0o777) == 0o600
