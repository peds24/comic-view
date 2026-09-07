# Google Sheets Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically mirror `data/library_comics.json` to a live Google Sheet every time a comic is added via `add-comic` or `check-pulls`, plus a manual `sync-sheet` command.

**Architecture:** A new pure-ish module, `library/sheets_sync.py`, owns Sheets API auth (OAuth, cached token) and the record→row mapping. `cli.py` calls its one public function, `sync_comics_to_sheet`, from three places: the new `sync-sheet` command, and — wrapped in try/except so failures only print a warning — the existing success paths of `check_pulls_cmd` and `add_comic_cmd`.

**Tech Stack:** `gspread` (Sheets API client), `google-auth` + `google-auth-oauthlib` (OAuth), Python 3.10+, `click`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-07-google-sheets-sync-design.md`

## Global Constraints

- Auth is OAuth as the user's own Google account (not a service account) — cached token in `secrets/google_token.json`, client secret in `secrets/google_client_secret.json`, both gitignored.
- Sync is a **full overwrite mirror**: every call clears the target worksheet and rewrites it from the current `library_comics.json` contents. No incremental diffing, no per-row upsert.
- Sheet columns, in order: `Title | Series | Issue # | Author | Year | Publisher | Status | Formats | Added Date`. No `description`, no internal bookkeeping fields (`id`, `upc`/`isbn`, `cover_path`, `metadata_source`, `preview_pages`).
- Rows sorted by `added_date` descending (newest first), ties broken by `id`.
- Scope is comics only — `library_manga.json` is never touched by this feature.
- At the two automatic call sites (`check_pulls_cmd`, `add_comic_cmd`), a Sheets failure is caught and printed as `Warning: could not sync to Google Sheets: {e}` — it must never raise, never block the local library update or git commit. If `google_sheets` isn't configured (`spreadsheet_id` unset), these call sites skip the sync entirely, silently.
- The manual `sync-sheet` command is the opposite: it lets errors propagate, and raises a clear `click.ClickException` if not configured.

---

### Task 1: `google_sheets` config support

**Files:**
- Modify: `library/config.py`
- Modify: `.gitignore`
- Modify: `config.example.yaml`
- Test: `tests/test_config.py` (new file)

**Interfaces:**
- Produces: `GoogleSheetsConfig` dataclass with fields `spreadsheet_id: str = ""`, `worksheet_name: str = "Comics"`, `client_secret_path: str = "secrets/google_client_secret.json"`, `token_path: str = "secrets/google_token.json"`, and property `is_configured: bool` (`True` iff `spreadsheet_id` is non-empty). `Config.google_sheets: GoogleSheetsConfig`, populated by `load_config` from an optional `google_sheets:` block in `config.yaml` (all fields optional, same "missing block → all defaults" behavior as `pull_list`/`google_books` today).

- [ ] **Step 1: Write the failing config tests**

Create `tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'google_sheets'`

- [ ] **Step 3: Add `GoogleSheetsConfig` and wire it into `Config`/`load_config`**

In `library/config.py`, add after `PullListConfig`:

```python
@dataclass
class GoogleSheetsConfig:
    spreadsheet_id: str = ""
    worksheet_name: str = "Comics"
    client_secret_path: str = "secrets/google_client_secret.json"
    token_path: str = "secrets/google_token.json"

    @property
    def is_configured(self) -> bool:
        return bool(self.spreadsheet_id)
```

Add a field to `Config`:

```python
@dataclass
class Config:
    roots: list[RootConfig]
    metron: MetronConfig
    google_books: GoogleBooksConfig
    data_dir: Path
    pull_list: PullListConfig
    google_sheets: GoogleSheetsConfig
```

In `load_config`, alongside the existing `*_raw` lines:

```python
    sheets_raw = raw.get("google_sheets", {}) or {}
```

and in the returned `Config(...)`, add:

```python
        google_sheets=GoogleSheetsConfig(
            spreadsheet_id=sheets_raw.get("spreadsheet_id", ""),
            worksheet_name=sheets_raw.get("worksheet_name", "Comics"),
            client_secret_path=sheets_raw.get("client_secret_path", "secrets/google_client_secret.json"),
            token_path=sheets_raw.get("token_path", "secrets/google_token.json"),
        ),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Run the full existing test suite to confirm nothing else broke**

Run: `pytest -q`
Expected: PASS (existing tests write `config.yaml` without a `google_sheets` block, which must still load fine with all-defaults)

- [ ] **Step 6: gitignore the secrets directory**

Add to `.gitignore` (after the `config.yaml` line, with a comment):

```
# OAuth client secret + cached token for Google Sheets sync — personal, never commit
secrets/
```

- [ ] **Step 7: Document the config block in `config.example.yaml`**

Append to `config.example.yaml`:

```yaml

# Optional — only needed for `comic-library sync-sheet` (and the
# automatic sync add-comic/check-pulls trigger). Set up a Google Cloud
# OAuth client (Desktop app type) with the Sheets API enabled, share
# nothing (this uses your own account via OAuth, not a service account),
# and download client_secret.json into secrets/. See
# docs/superpowers/specs/2026-09-07-google-sheets-sync-design.md.
google_sheets:
  spreadsheet_id: "your-spreadsheet-id-from-the-sheet-url"
  worksheet_name: "Comics"
  client_secret_path: "secrets/google_client_secret.json"
  token_path: "secrets/google_token.json"
```

- [ ] **Step 8: Commit**

```bash
git add library/config.py tests/test_config.py .gitignore config.example.yaml
git commit -m "Add google_sheets config block for Sheets sync"
```

---

### Task 2: Record→row mapping (`library/sheets_sync.py`, pure part)

**Files:**
- Create: `library/sheets_sync.py`
- Test: `tests/test_sheets_sync.py` (new file)

**Interfaces:**
- Consumes: `ComicRecord` from `library.models` (fields: `title`, `series`, `issue_number`, `author`, `year`, `publisher`, `status`, `formats`, `added_date` — see `library/models.py:13-32`).
- Produces: `_HEADER: list[str]` and `_comic_to_row(record: ComicRecord) -> list[str]`, both used by Task 3's `sync_comics_to_sheet`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sheets_sync.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'library.sheets_sync'`

- [ ] **Step 3: Create `library/sheets_sync.py` with the mapping**

```python
"""Mirrors data/library_comics.json to a live Google Sheet.

Full-overwrite sync only: every sync_comics_to_sheet call clears the
target worksheet and rewrites it from the current library contents.
Deliberately not incremental — see
docs/superpowers/specs/2026-09-07-google-sheets-sync-design.md.
"""
from __future__ import annotations

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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add library/sheets_sync.py tests/test_sheets_sync.py
git commit -m "Add comic-record-to-sheet-row mapping"
```

---

### Task 3: OAuth + `sync_comics_to_sheet`

**Files:**
- Modify: `library/sheets_sync.py`
- Modify: `pyproject.toml`
- Test: `tests/test_sheets_sync.py`

**Interfaces:**
- Consumes: `Config`/`GoogleSheetsConfig` from Task 1 (`config.google_sheets.spreadsheet_id`, `.worksheet_name`, `.client_secret_path`, `.token_path`); `_HEADER`/`_comic_to_row` from Task 2.
- Produces: `sync_comics_to_sheet(records: dict[str, ComicRecord], config: Config) -> None` — the one function Tasks 4-6 call. Internally uses a private `_authorize(config: Config)` that Task's own tests monkeypatch (`library.sheets_sync._authorize`) to avoid any real network/OAuth call.

- [ ] **Step 1: Add the new dependencies**

In `pyproject.toml`, add to `dependencies`:

```toml
    "gspread>=6.1",
    "google-auth>=2.29",
    "google-auth-oauthlib>=1.2",
```

Run: `pip install -e .`
Expected: installs `gspread`, `google-auth`, `google-auth-oauthlib` (and their transitive deps) into the active virtualenv.

- [ ] **Step 2: Write the failing test for `sync_comics_to_sheet`**

Append to `tests/test_sheets_sync.py`:

```python
from library.config import Config, GoogleSheetsConfig, MetronConfig, GoogleBooksConfig, PullListConfig
from library.sheets_sync import sync_comics_to_sheet


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
```

(`_record` and `_HEADER` are already imported/defined earlier in this file from Task 2.)

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: FAIL — `ImportError: cannot import name 'sync_comics_to_sheet'`

- [ ] **Step 4: Implement `_authorize` and `sync_comics_to_sheet`**

Add these imports to the top of `library/sheets_sync.py`, alongside the
existing `from library.models import ComicRecord` (all imports together,
not scattered mid-file):

```python
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from library.config import Config
```

Then add this below the existing `_HEADER`/`_comic_to_row` code (still in
`library/sheets_sync.py`):

```python
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
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), _SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
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
```

(`ComicRecord` here is the same import already at the top of the file from Task 2 — no new import needed for it.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add library/sheets_sync.py pyproject.toml tests/test_sheets_sync.py
git commit -m "Add OAuth-backed sync_comics_to_sheet"
```

---

### Task 4: `sync-sheet` CLI command

**Files:**
- Modify: `cli.py`
- Test: `tests/test_cli_sync_sheet.py` (new file)

**Interfaces:**
- Consumes: `sync_comics_to_sheet` (Task 3), `load_config`/`load_library` (already imported in `cli.py`).
- Produces: `comic-library sync-sheet --config <path>` — the manual command; also the first place a user runs the interactive OAuth consent flow.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_sync_sheet.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_cli_sync_sheet.py -v`
Expected: FAIL — `Error: No such command 'sync-sheet'`

- [ ] **Step 3: Add the import and command to `cli.py`**

Add to the imports at the top of `cli.py` (alongside the other `library.*` imports):

```python
from library.sheets_sync import sync_comics_to_sheet
```

Add the command (near `serve`, at the end of the file):

```python
@main.command("sync-sheet")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
def sync_sheet_cmd(config_path: str) -> None:
    """Pushes the current comics library to the configured Google Sheet
    (full overwrite of the configured worksheet). Also the command to run
    for the first-time OAuth consent flow. Unlike the automatic sync
    add-comic/check-pulls trigger, errors here are not swallowed — this
    command's whole purpose is the sync itself."""
    config = load_config(config_path)
    if not config.google_sheets.is_configured:
        raise click.ClickException(
            "google_sheets not configured — fill in config.yaml "
            "(see docs/superpowers/specs/2026-09-07-google-sheets-sync-design.md)."
        )
    library_path = config.data_dir / "library_comics.json"
    records = load_library(library_path)
    sync_comics_to_sheet(records, config)
    click.echo(f"Synced {len(records)} comic(s) to the '{config.google_sheets.worksheet_name}' worksheet.")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_cli_sync_sheet.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli_sync_sheet.py
git commit -m "Add sync-sheet CLI command"
```

---

### Task 5: Auto-sync from `check-pulls`

**Files:**
- Modify: `cli.py` (`check_pulls_cmd`, around `cli.py:243-269`)
- Test: `tests/test_cli_check_pulls.py`

**Interfaces:**
- Consumes: `sync_comics_to_sheet` (Task 3, already imported into `cli.py` in Task 4).

- [ ] **Step 1: Extend the test config helper and write the failing tests**

In `tests/test_cli_check_pulls.py`, change `_write_config` to accept an optional `google_sheets` block:

```python
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
```

Add new tests at the end of the file:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_cli_check_pulls.py -v`
Expected: FAIL — the new assertions about "Synced to Google Sheets." find no such output, and `_fail_if_called` is never exercised so that test passes vacuously today (confirm the first two fail; that's the meaningful signal).

- [ ] **Step 3: Add the sync call to `check_pulls_cmd`**

In `cli.py`, inside `check_pulls_cmd`, immediately after the existing git-commit `try`/`except` block (right after the line `click.echo(f"Warning: could not commit to git: {e}")`, still inside the `if pending:` block), add:

```python
        if (added or merged) and config.google_sheets.is_configured:
            try:
                sync_comics_to_sheet(records, config)
                click.echo("Synced to Google Sheets.")
            except Exception as e:
                click.echo(f"Warning: could not sync to Google Sheets: {e}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_cli_check_pulls.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli_check_pulls.py
git commit -m "Auto-sync to Google Sheets after check-pulls"
```

---

### Task 6: Auto-sync from `add-comic`

**Files:**
- Modify: `cli.py` (`add_comic_cmd`, around `cli.py:316-349`)
- Test: `tests/test_cli_add_comic.py`

**Interfaces:**
- Consumes: `sync_comics_to_sheet` (Task 3, already imported into `cli.py` in Task 4).

**Note:** `add_comic_cmd`'s "new record" save path (`cli.py:347-349`, the `records[record.id] = record; save_library(...)` branch) has no existing git-commit call to piggyback on — only the "merge into existing" branch commits today. That's a pre-existing gap, out of scope for this plan; the sync call is added independently of git-commit in both branches.

- [ ] **Step 1: Extend the test config helper and write the failing tests**

In `tests/test_cli_add_comic.py`, change `_write_config` to accept an optional `google_sheets` block:

```python
def _write_config(tmp_path: Path, google_sheets: dict | None = None) -> Path:
    config_path = tmp_path / "config.yaml"
    data = {"roots": [{"path": str(tmp_path), "type": "comic"}]}
    if google_sheets:
        data["google_sheets"] = google_sheets
    config_path.write_text(yaml.dump(data))
    return config_path
```

Add new tests at the end of the file:

```python
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

    def _fail_if_called(records, config):
        raise AssertionError("sync_comics_to_sheet should not be called when not configured")
    monkeypatch.setattr("cli.sync_comics_to_sheet", _fail_if_called)

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)], input="y\n")

    assert result.exit_code == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_cli_add_comic.py -v`
Expected: FAIL — the sync-related assertions (`len(synced_with) == 1`, the warning message) aren't satisfied yet.

- [ ] **Step 3: Add the sync calls to `add_comic_cmd`**

In `cli.py`, inside `add_comic_cmd`'s "merge into existing" branch, right after its existing git-commit `try`/`except` block and before the `return` (i.e. right after `click.echo(f"Warning: could not commit to git: {e}")`, still inside `if changed:`), add:

```python
            if config.google_sheets.is_configured:
                try:
                    sync_comics_to_sheet(records, config)
                except Exception as e:
                    click.echo(f"Warning: could not sync to Google Sheets: {e}")
```

And at the end of the function, right after the final `click.echo(f"Added {record.series or record.title} #{record.issue_number or '?'} ({record.id}) as {new_format}.")`, add:

```python
    if config.google_sheets.is_configured:
        try:
            sync_comics_to_sheet(records, config)
        except Exception as e:
            click.echo(f"Warning: could not sync to Google Sheets: {e}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_cli_add_comic.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli_add_comic.py
git commit -m "Auto-sync to Google Sheets after add-comic"
```

---

## Post-implementation (manual, not part of the automated tasks)

These are one-time setup steps only the user can do (they require the user's own Google account and this specific spreadsheet):

1. In Google Cloud Console, create a project, enable the Google Sheets API, configure the OAuth consent screen (External, publishing status **"In production"** — not "Testing", to avoid the 7-day refresh-token expiry — accepting the "unverified app" warning during consent), and create an OAuth client ID of type **Desktop app**. Download it as `secrets/google_client_secret.json`.
2. Fill in `config.yaml`'s `google_sheets` block with the real spreadsheet ID from the sheet's URL (`https://docs.google.com/spreadsheets/d/<THIS_PART>/edit`) and the tab name to write to.
3. Run `comic-library sync-sheet` once — this opens a browser for the one-time OAuth consent and caches `secrets/google_token.json`. Confirm the sheet gets overwritten with the current library.
4. From then on, `add-comic` and `check-pulls` auto-sync after every successful add.
