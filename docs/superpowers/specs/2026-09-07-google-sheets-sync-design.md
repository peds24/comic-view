# Google Sheets sync — design

## Background

The user maintains a live Google Sheet
(`https://docs.google.com/spreadsheets/d/1HSOcBUg7-6lkEkDi0D5RAiFnUBa-cpcCj7tyYx7dqdE/edit`)
that they want kept in sync with `data/library_comics.json` — so they (or
anyone they share the sheet with) can browse the comics collection without
needing this repo or the viewer. Today nothing in this codebase talks to
any Google API besides the read-only Google Books lookup used by
`enrich` (`library/metadata_sources/google_books.py`, a plain API-key HTTP
call — no auth flow, no write access). This is the first integration that
needs to *write* to a Google service on the user's behalf.

## Decisions already made (with the user, in conversation)

- **Auth: OAuth as the user's own Google account**, not a service account.
  A service account would need the sheet explicitly shared with a robot
  email and is simpler to run unattended, but the user chose OAuth — the
  sheet stays edited "as them." One-time browser consent, cached token
  refreshed silently afterward.
- **Sync strategy: full overwrite mirror**, not incremental append/upsert.
  Every sync clears the target worksheet tab and rewrites it from the
  current `library_comics.json` contents. Simpler, never drifts or
  duplicates, sheet always exactly matches the database. Trade-off the
  user accepted: any manual edits made directly in the Sheet (a notes
  column, checking things off, etc.) get clobbered on the next sync —
  the sheet is a mirror, not a place to keep independent data.
- **Trigger: automatic**, not a manual-only command. Right after
  `check_pulls_cmd` and `add_comic_cmd` finish updating
  `library_comics.json` (and, for `check_pulls_cmd`, right alongside the
  existing local git auto-commit), the sheet sync runs too — no extra
  step for the user to remember. A manual `sync-sheet` command is added
  as well, for the first-time OAuth consent run and for forcing a refresh
  independent of adding a comic.
- **Scope: comics only.** `library_manga.json` is not synced — this
  matches how `add-comic`/`check-pulls` already only ever touch the
  comics file (manga has no pull-list or single-URL-add flow today).
- **Columns**: `Title | Series | Issue # | Author | Year | Publisher |
  Status | Formats | Added Date`. `description` is left out (too long for
  a spreadsheet cell); internal bookkeeping fields (`id`, `upc`/`isbn`,
  `cover_path`, `metadata_source`, `preview_pages`) are left out as
  uninteresting to a human browsing the sheet. Rows are sorted by
  `added_date` descending, so newly added comics appear at the top.
- **Failures never block the CLI.** A Sheets API/auth/network error is
  caught and printed as a warning, exactly like the existing
  `commit_if_changed` error handling in `check_pulls_cmd`/`add_comic_cmd`
  — the comic is still added to the local library and committed to git
  even if the Sheets push fails.

## Architecture

New module `library/sheets_sync.py`, using `gspread` for the Sheets API
calls and `google-auth-oauthlib` for the OAuth flow. Two public pieces:

- `_comic_to_row(record: ComicRecord) -> list[str]` — pure mapping
  function, no network, easily unit-tested.
- `sync_comics_to_sheet(records: dict[str, ComicRecord], config: Config) ->
  None` — authenticates (loading/refreshing a cached token, or running
  the interactive consent flow if no valid token exists yet), opens the
  configured spreadsheet + worksheet, clears it, and writes the header
  row plus one row per comic (sorted by `added_date` descending).

`records` here is the same `dict[str, ComicRecord]` shape already
produced by `load_library` and used throughout `cli.py` — no new loading
path needed.

## Auth flow (OAuth, one-time setup)

1. In Google Cloud Console: create a project, enable the Google Sheets
   API, configure the OAuth consent screen (External, with the user added
   as a test user — this is a personal single-user integration, not a
   published app), create an OAuth client ID of type **Desktop app**,
   download the resulting `client_secret.json`.
2. First run of anything that calls `sync_comics_to_sheet` (most likely
   the new manual `sync-sheet` command, run once deliberately):
   `google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(...).run_local_server()`
   opens a browser for the user to log in and approve `spreadsheets`
   scope access. The resulting credentials (including refresh token) are
   cached to `token.json`.
3. Every subsequent call: loads `token.json`, refreshes the access token
   silently via the refresh token if expired. No browser interaction
   unless the user revokes access from their Google account, in which
   case the next call fails with a clear auth error (caught and reported
   as a warning per the "never blocks the CLI" rule above) — re-running
   `sync-sheet` interactively re-triggers the consent flow.

**Known gotcha**: if the OAuth consent screen is left in Google's
"Testing" publishing status, refresh tokens for test users expire after
7 days, which would silently break the automatic sync every week
(surfaced only as a warning, easy to miss) until someone notices and
re-runs `sync-sheet` to re-consent. Since this is a single-user personal
tool requesting a sensitive-but-not-restricted scope
(`spreadsheets`), set the consent screen's publishing status to **"In
production"** without going through Google's verification — this shows
an "unverified app" warning during the one-time consent click-through
but avoids the 7-day expiry entirely. This is a one-time setup choice,
not something the code needs to handle.

Both `client_secret.json` and `token.json` are personal secrets — like
`config.yaml` itself, they must never be committed. They live in a new
`secrets/` directory at the repo root, which `.gitignore` excludes
entirely.

## Config

`config.yaml` (and `config.example.yaml` as a documented placeholder)
gets a new optional block:

```yaml
# Optional — only needed for `comic-library sync-sheet` (and the
# automatic sync that add-comic/check-pulls trigger). Set up a Google
# Cloud OAuth client (Desktop app type) and Sheets API access first —
# see docs/superpowers/specs/2026-09-07-google-sheets-sync-design.md.
google_sheets:
  spreadsheet_id: "1HSOcBUg7-6lkEkDi0D5RAiFnUBa-cpcCj7tyYx7dqdE"
  worksheet_name: "Comics"
  client_secret_path: "secrets/google_client_secret.json"
  token_path: "secrets/google_token.json"
```

`library/config.py`'s `Config` dataclass gets a matching
`google_sheets` section, following the existing pattern used for
`metron`/`google_books`/`pull_list` (an `is_configured` property that
checks `spreadsheet_id` is set, so callers can no-op cleanly when the
user hasn't set this up).

## Data mapping

For each `ComicRecord`, one row:

| Column | Source |
|---|---|
| Title | `f"{series} #{issue_number}"` if both are set, else `record.title` (same fallback rule already used for previews in `_echo_comic_preview`'s callers) |
| Series | `record.series or ""` |
| Issue # | `record.issue_number or ""` |
| Author | `record.author or ""` |
| Year | `record.year or ""` |
| Publisher | `record.publisher or ""` |
| Status | `record.status` |
| Formats | `", ".join(record.formats)` |
| Added Date | `record.added_date` |

Header row is written first, then one row per record, sorted by
`added_date` descending (ties broken by `id` for a stable order across
runs).

## Trigger integration

- **`check_pulls_cmd`** (`cli.py`): after the existing
  `commit_if_changed(...)` block, if any records were actually
  added/merged this run, call `sync_comics_to_sheet`. Wrapped in its own
  try/except printing `Warning: could not sync to Google Sheets: {e}` —
  mirrors the existing git-commit warning handling immediately above it.
  No-ops (skips the call entirely) if `config.google_sheets.is_configured`
  is false, so users who haven't set this up see no change in behavior.
- **`add_comic_cmd`** (`cli.py`): same call + same try/except, at both
  `save_library` call sites (the "merged into existing" early-return path,
  and the "new record" path at the end).
- **New `sync-sheet` command**: takes no arguments beyond `--config`,
  loads `library_comics.json`, and calls `sync_comics_to_sheet` directly
  — raising (not warning) on failure, since this command's whole purpose
  is the sync itself and silent failure would be useless. This is also
  the natural place to run the first-time OAuth consent flow.

## Error handling

- Sheets API/auth/network errors from the two automatic call sites
  (`check_pulls_cmd`, `add_comic_cmd`) are caught and printed as a
  warning; they never raise, never block the local library update or git
  commit.
- The manual `sync-sheet` command lets errors propagate as a
  `click.ClickException` (or the underlying exception), since a user
  running it explicitly wants to know if the sync failed.
- Not configured (`google_sheets.spreadsheet_id` unset in `config.yaml`):
  automatic call sites silently skip; `sync-sheet` itself raises a clear
  `click.ClickException` telling the user to configure it.

## Testing

- Unit test `_comic_to_row` against fixture `ComicRecord`s covering: both
  series+issue set, only title set, missing optional fields (author/year/
  publisher all `None`), multiple formats.
- Unit test `sync_comics_to_sheet` with the `gspread` client mocked out
  (patch the module-level function that builds/returns the authorized
  client), asserting the worksheet's `clear()` is called and `update()` /
  equivalent is called with the exact expected 2D row list (header +
  rows sorted by `added_date` descending) — matching the mocking style
  already used for subprocess calls in `tests/test_git_utils.py`.
- No test exercises real OAuth or a real network call to Google.

## New dependencies

`gspread`, `google-auth`, `google-auth-oauthlib` — added to
`pyproject.toml`'s `dependencies`.

## Out of scope (explicitly)

- Syncing `library_manga.json` — comics only, per the decision above.
- Any UI in the Sheet itself (formatting, conditional formatting, charts)
  — this only ever writes plain row data.
- Handling the case where the user renames/deletes the worksheet tab or
  the spreadsheet itself out of band; the next sync will simply fail with
  a Sheets API error, surfaced per the error-handling rules above.
- Migrating existing manual edits already in the live Sheet — the first
  sync overwrites whatever is there today with a fresh mirror of
  `library_comics.json`.
