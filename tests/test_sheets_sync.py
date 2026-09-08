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
    assert len(_HEADER) == len(_comic_to_row(_record()))


def test_comic_to_row_uses_series_and_issue_for_title():
    row = _comic_to_row(_record())
    assert row == [
        "Absolute Batman #16", "Absolute Batman", "16", "Scott Snyder",
        "2026", "DC Comics", "unread", "digital", "2026-09-07",
    ]


def test_comic_to_row_falls_back_to_title_without_series_or_issue():
    record = _record(title="Some One-Shot", series=None, issue_number=None)
    row = _comic_to_row(record)
    assert row[0] == "Some One-Shot"
    assert row[1] == ""
    assert row[2] == ""


def test_comic_to_row_blanks_missing_optional_fields():
    record = _record(author=None, year=None, publisher=None)
    row = _comic_to_row(record)
    assert row[3] == ""  # author
    assert row[4] == ""  # year
    assert row[5] == ""  # publisher


def test_comic_to_row_joins_multiple_formats():
    record = _record(formats=["digital", "print"])
    row = _comic_to_row(record)
    assert row[7] == "digital, print"


from library.config import Config, GoogleSheetsConfig, MetronConfig, GoogleBooksConfig, PullListConfig
from library.sheets_sync import sync_comics_to_sheet, _authorize


class _FakeWorksheet:
    def __init__(self):
        self.cleared = False
        self.updated_with = None

    def clear(self):
        self.cleared = True

    def update(self, rows):
        self.updated_with = rows


class _FakeSheet:
    def __init__(self, worksheet):
        self._worksheet = worksheet

    def worksheet(self, name):
        self._requested_name = name
        return self._worksheet


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
    assert worksheet.updated_with[1][1] == "Newer"  # sorted by added_date descending
    assert worksheet.updated_with[2][1] == "Older"
    assert client._requested_key == "abc123"
    assert client._sheet._requested_name == "Comics"


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
