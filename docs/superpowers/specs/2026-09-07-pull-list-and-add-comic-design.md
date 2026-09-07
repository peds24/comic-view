# Pull-list automation + `add-comic` CLI — design

## Background

Right now every comic/manga enters the library through a bulk path: the
digital scanner (`scan`), or the physical Excel importer
(`import-physical`). There's no lightweight way to add a single comic the
moment it's known about — either because it just shipped on the user's
comic-shop pull list (physical), or because the user bought it digitally
outside the pull list.

The user tracks their pull list on League of Comic Geeks
(`leagueofcomicgeeks.com/profile/peds24/pull-list`), which also exposes a
per-user ICS calendar feed (`leagueofcomicgeeks.com/member/calendar_ics/peds24`)
listing what ships each week. Individual issues also each have their own
Comic Geeks page, which `library/metadata_sources/comic_geeks.py` already
knows how to parse (used today by the manual-attach-link feature in the
viewer).

## Spike findings (both confirmed live this session)

**1. Comic Geeks now sits behind a Cloudflare managed challenge.** A plain
`requests`/`curl` GET — what `comic_geeks.py` and every other metadata
source in this codebase uses via `http_utils.get_with_retry` — gets a 403
with `cf-mitigated: challenge`. This is new since the manual-attach-link
feature was built; the existing `comic_geeks.fetch_issue()` was tested live
in this session and returns `{}` on a real issue URL. Headless Playwright
Chromium, already available in the project's `.venv`, does get through:
fetching `https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16`
via Playwright returned the full real page (`<h1>Absolute Batman #16</h1>`).
Cover images are hosted on `s3.amazonaws.com`, not behind Cloudflare, so
cover downloads are unaffected — only the HTML page fetch needs to change
transport.

**2. The ICS calendar has no per-comic Comic Geeks links.** Each `VEVENT`
is plain text — a release date and a `DESCRIPTION` blob listing one or more
titles and prices, e.g.:

```
SUMMARY:New Comics for 10/07
DESCRIPTION:Batman #423 Facsimile Edition 2026\n$3.99\n\nMidnight Spider-Man #1\n$5.99\n\nBatman #14\n$4.99\n\nThe Demon #1\n$3.99\n\n...
DTSTART;VALUE=DATE:20261007
```

So resolving a pulled title to real metadata means a title-based lookup,
not following a link. The ICS is fetchable via Playwright the same way
(confirmed live — it's served as a file download in a real browser, caught
via Playwright's `expect_download`).

## Decisions made with the user

- **Weekly resolution uses Metron's existing title/series search**, not a
  new Comic Geeks search scraper. Comic Geeks stays scoped to: providing
  the calendar, and parsing a specific issue page when the user pastes its
  link (`add-comic`). This avoids building and maintaining a second
  scraper against a moving target.
- **When Metron's title resolution is ambiguous or fails, the weekly job
  must flag it for the user rather than guess.** Concrete failure mode the
  user has hit before: Metron has multiple series named exactly "Batman"
  across different eras (an ended run and the current `batman-2025`
  relaunch); `MetronSource._find_series` already narrows by year when one
  is given, but falls back to "first exact match" whenever that doesn't
  cleanly resolve — silently risking the wrong series. See "Confidence-
  checked Metron resolution" below for the fix.
- **Every line in a pull-list event is added as its own record** — including
  what looks like a duplicate/variant line (e.g. a base cover and a named
  variant of the same issue both pulled the same week) or a bundle of
  unrelated titles under one calendar day. This matches what's literally on
  the pull list; a stray unwanted line is easy to delete afterward via the
  viewer's existing per-card delete control.
- **The weekly check runs as a scheduled Claude routine** (via the
  `schedule` skill), not a plain deterministic cron script — it needs
  judgment on messy/ambiguous titles and reports back to the user, which a
  pure script can't do.
- **The routine commits its changes locally but never pushes.** Push stays
  a manual, reviewed action.
- **`add-comic <url>` defaults to digital**, matching the user's stated
  primary manual use case (a digital comic bought outside the pull list); a
  `--physical` flag covers a one-off physical add outside the automated
  weekly flow.

## Components

### 1. Headless-browser fetch helper (new: `library/browser_fetch.py`)

Two functions, both backed by a single headless Playwright Chromium
launch per call (short-lived — this is a low-volume, occasional-use tool,
not a hot path, so launch overhead per call is an acceptable trade for not
managing a long-lived browser process):

- `fetch_html(url: str, *, wait_selector: str = "h1", timeout_ms: int = 20000) -> str`
  Navigates with `wait_until="domcontentloaded"`, then waits for
  `wait_selector` to appear (catching the outer navigation timeout the
  spike hit — the page finishes rendering before Playwright's `load` event
  fires, so `goto`'s own timeout is expected and ignored as long as the
  selector shows up). Returns `page.content()`. Returns `""` on any
  failure (page never resolves, selector never appears, network error) —
  callers already treat an empty/unparseable result as "couldn't read this
  page," matching today's `except Exception: return {}` behavior in
  `comic_geeks.fetch_issue`.
- `download_text(url: str, *, timeout_ms: int = 20000) -> str`
  For endpoints a real browser treats as a file download (the ICS feed).
  Uses `page.expect_download()`, saves to a temp path, reads it back as
  text, returns `""` on failure.

Both use the same realistic desktop User-Agent already hardcoded in
`comic_geeks.py` today.

### 2. `library/metadata_sources/comic_geeks.py` — swap transport only

`fetch_issue`'s single `get_with_retry(...)` call is replaced with
`browser_fetch.fetch_html(resolved_url)`. All existing BeautifulSoup
parsing (`_extract_writer`, `_extract_year`, `_extract_publisher`,
`_extract_upc`, `_extract_cover_url`) is unchanged — same DOM, same
selectors, confirmed against a live fetch this session. Existing tests
(`tests/test_comic_geeks.py`) mock the HTTP call today; they're updated to
mock `browser_fetch.fetch_html` instead, so no real browser launches in
the test suite.

### 3. Confidence-checked Metron resolution (new method on `MetronSource`)

```python
def find_issue_confident(
    self, series: str, number: str, year: int | None
) -> tuple[dict | None, str, list[dict]]:
    """Returns (issue_detail_or_None, status, candidates).

    status is one of:
      "ok"        — exactly one series named `series` actually has an
                    issue #`number`; that issue is returned.
      "not_found" — no series named `series` has an issue #`number`.
      "ambiguous" — more than one series named `series` has an issue
                    #`number` (e.g. two different eras/relaunches both
                    reached that issue number); none is returned, and
                    `candidates` lists each match (series id, publisher,
                    year_began-year_end) for a human to disambiguate.
    """
```

Implementation: fetch every series result from `/series/?name=<series>`
whose normalized name exactly matches `series` (same exact-match filter
`_find_series` already applies) — not just the year-narrowed pick. For
each exact-name candidate, query `/issue/?series_id=<id>&number=<number>`.
Keep only candidates that actually return a hit. Zero hits → `not_found`.
One hit → `ok`, return its full issue detail. More than one → `ambiguous`,
return `None` plus the candidate list (no fetched issue detail needed —
just enough for the flag report: series id, publisher name, year range).

This directly fixes the reported failure mode: two Batman-named series
both existing in the ended/relaunch case only collide if *both* happen to
have an issue matching the exact pulled number — an actual bug is a real
ambiguity worth surfacing, but the far more common case (only the current
run has reached issue #14) now resolves confidently without a `year` hint
being available at all, no year even needed. `_find_series` /
`find_issue_by_series_and_number` (used by the physical Excel importer)
are untouched — this is an additive method for the weekly job, which needs
the "don't ever guess wrong" property; the existing importer's more lenient
behavior stays as-is since it's out of scope here.

### 4. Pull calendar parsing (new: `library/pull_calendar.py`)

```python
@dataclass
class PulledItem:
    event_uid: str      # ICS VEVENT UID — stable across weekly runs
    release_date: date  # from DTSTART
    title: str          # one line of the event's DESCRIPTION, e.g. "Batman #14"
    price: str | None   # e.g. "$4.99", or None if blank/unparseable

def fetch_pulled_items(calendar_url: str) -> list[PulledItem]: ...
```

Uses `browser_fetch.download_text` to get the raw ICS, then Python's
`icalendar` package (new dependency — a small, well-established ICS
parser; hand-rolling VEVENT/line-folding parsing isn't worth it) to walk
`VEVENT`s. Each `DESCRIPTION` is unescaped (`\n` → newline, per the RFC
5545 escaping Comic Geeks' export uses) and split into title/price pairs:
non-blank lines alternate title, price, blank-separator, based on the
consistent shape confirmed in the live feed this session. A line that
doesn't look like a price (`$` prefix) is treated as `price=None` rather
than misaligning the rest of the pairs.

### 5. Pull resolver (new: `library/pull_resolver.py`)

```python
def resolve_and_add(
    item: PulledItem,
    records: dict[str, ComicRecord],
    metron: MetronSource,
    covers_dir: Path,
) -> ResolverOutcome:  # "added" | "merged" | "flagged"
```

- Extracts `issue_number` via the existing `matching.extract_issue`, and
  `series` by stripping the `#N` suffix (mirrors what
  `comic_geeks.fetch_issue` already does for a page's `<h1>`).
- **Single issue, number extracted, and `matching.is_matchable`** (i.e.
  not a TP/HC/omnibus/annual/variant/collection-worded title): calls
  `metron.find_issue_confident(series, issue_number, item.release_date.year)`.
  - `"ok"` → build a `ComicRecord` (`formats=["print"]`, same field-fill +
    cover-download shape as `_apply_metron_issue` in
    `physical_importer.py`), merge into an existing digital match via
    `matching.find_digital_match` if one exists (append `"print"` to its
    `formats` instead of duplicating — identical to the physical
    importer's existing behavior), else add as new. Returns `"merged"` or
    `"added"`.
  - `"not_found"` or `"ambiguous"` → no record written; returns
    `"flagged"` with a reason string (and, for `"ambiguous"`, the
    candidate list) for the weekly summary.
- **Not matchable this way** (TP/HC/omnibus/annual/variant/collection
  wording, or no issue number extracted): best-effort
  `metron.search(title, item.release_date.year)` (the existing, more
  lenient method) to fill what it can; if it returns nothing at all,
  outcome is `"flagged"` ("no Metron match — needs a manual `add-comic`
  link or review") rather than saving a bare stub with only a title.

### 6. ID scheme for records this flow creates

Priority order, first available wins:

1. **UPC on the resolved/fetched data** (Metron issue detail, or Comic
   Geeks' own `_extract_upc`) → `upc-<code>`, consistent with the physical
   importer's existing scheme — same dedupe semantics as an Excel import
   of that same barcode.
2. **A `add-comic` add with no UPC** → `cgeeks-<comic-id>`, the numeric id
   from the pasted Comic Geeks URL (`/comic/<id>/...`). Stable across
   re-runs since it comes from the URL itself, not from when it was added.
3. **A weekly-job single-issue confident match (`find_issue_confident`
   status `"ok"`) with no UPC** → `metron-<issue_id>`, the resolved issue's
   own Metron database id (present on every issue detail response,
   independent of barcode availability). This matters because a shipment
   delay can cause the same comic to appear in a *later* week's calendar
   entry (a different `event_uid`, so the `pull_state.json` UID-dedupe
   wouldn't catch it) — anchoring the id to the actual matched issue
   rather than to the pull date means re-resolving it a second time still
   lands on the same record instead of creating a duplicate.
4. **A weekly-job best-effort match** (TP/HC/omnibus/annual/variant title,
   resolved via the lenient `metron.search`, which returns a metadata dict
   with no issue id to anchor to) → `pull-<release_date isoformat>-<slugified title>`.
   This is the one case where a re-pulled duplicate under a different
   event isn't caught — accepted as a rare, low-cost edge case (a stray
   duplicate collected-edition record is easy to spot and delete in the
   viewer) rather than engineering around it.

### 7. `add-comic` CLI (new Click command in `cli.py`)

```python
@main.command("add-comic")
@click.argument("url")
@click.option("--config", "config_path", default="config.yaml")
@click.option("--physical", is_flag=True, help="Add as a physical copy instead of digital (default).")
def add_comic_cmd(url: str, config_path: str, physical: bool) -> None: ...
```

- Rejects non-`leagueofcomicgeeks.com` URLs immediately with a clear
  error (reusing `comic_geeks.is_comic_geeks_url`).
- `info = comic_geeks.fetch_issue(url)`; empty result → clear error
  ("Couldn't read that Comic Geeks page — check the URL, or the site may
  be unreachable") and non-zero exit, no partial record written.
- Id: `upc-<code>` if `info["upc"]` present, else `cgeeks-<comic-id>`
  parsed from the URL.
- If that id already exists in `library_comics.json`: add the requested
  format to it if missing (no duplicate), report "already in your
  library — added digital/print to its formats."
- Else, if a same-series/issue match exists in the *other* format (a
  digital record already there and this is `--physical`, or vice versa —
  new small helper generalizing `matching.find_digital_match` to search
  either direction): merge the new format into that record instead of
  creating a second one.
- Else: create a new `ComicRecord` (`type="comic"`, requested format),
  fill fields from `info`, download the cover via `covers.download_cover`,
  add to `library_comics.json`.
- Prints a one-line confirmation: title, series/issue, id, format added.

### 8. `add-comic` shell wrapper

`bin/add-comic` (new, executable):

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "/Users/pedrosh/personal_projects/comic-view-ui"
exec .venv/bin/comic-library add-comic "$@"
```

A hardcoded absolute path rather than resolving `$0`'s directory — this is
a single-machine, single-checkout personal tool, and a hardcoded path
survives being invoked through a shell alias (which doesn't preserve
`$0` the way a symlink would). One line added to the user's `~/.zshrc`:

```bash
alias add-comic="/Users/pedrosh/personal_projects/comic-view-ui/bin/add-comic"
```

`cd`-ing into the repo first is required because `config.yaml` and
`data/` are resolved relative to the working directory throughout the
codebase (same assumption `serve` already makes) — this makes `add-comic`
work from any directory as asked, without changing that convention
everywhere else.

### 9. Weekly pull-list routine (scheduled Claude routine, via the `schedule` skill)

On each run:

1. `fetch_pulled_items(calendar_url)`.
2. Load `data/pull_state.json` (new — `{"processed_uids": [...]}`, git-
   tracked so state survives across machines/branches the same way the
   library files do). Skip any item whose `event_uid` is already in
   `processed_uids`.
3. Skip any item whose `release_date` is in the future (comics that
   haven't shipped yet stay on the calendar for weeks ahead of time in
   this feed — only process what's already released).
4. For each remaining item, `pull_resolver.resolve_and_add(...)`.
5. Add every processed item's `event_uid` to `processed_uids` regardless
   of outcome (added/merged/flagged) — a flagged item is reported once,
   not re-flagged every week; the user resolves it manually via
   `add-comic` if they want it added.
6. Save `library_comics.json` and `pull_state.json`.
7. `git commit` (no push) with a message summarizing the date range
   covered and counts.
8. Report to the user: N added, M merged into existing digital records,
   list of anything flagged with its reason.

## Testing

- `tests/test_browser_fetch.py`: since this wraps Playwright directly, unit
  tests mock at the Playwright API boundary (a fake `sync_playwright()`
  context) rather than launching a real browser — keeps the suite fast and
  network-free, matching how every other metadata source is tested today.
- `tests/test_comic_geeks.py`: existing tests updated to mock
  `browser_fetch.fetch_html` instead of `get_with_retry`; assertions on
  the parsed output are unchanged.
- `tests/test_metron.py`: new cases for `find_issue_confident` covering
  `"ok"` (single matching series), `"ambiguous"` (two series both have
  that issue number — the reported Batman scenario), and `"not_found"`.
- `tests/test_pull_calendar.py`: new — parses a fixture ICS (a trimmed
  version of the real feed shape captured this session, with the
  multi-title and blank-price cases) into expected `PulledItem`s.
- `tests/test_pull_resolver.py`: new — covers add / merge-into-digital /
  flag-ambiguous / flag-not-found / TP-and-omnibus-best-effort paths, with
  mocked `MetronSource`.
- `tests/test_cli.py` (new, or extend if one exists): `add-comic` happy
  path, already-exists merge path, bad-URL rejection, unreadable-page
  rejection — via Click's `CliRunner`, mocking `comic_geeks.fetch_issue`.

## Out of scope

- Building a Comic Geeks title-search scraper (explicitly decided against
  — Metron search covers this).
- Auto-pushing the weekly routine's commits.
- Changing how the existing `import-physical` Excel flow or the viewer's
  manual-attach-link feature resolve ambiguous series — `find_issue_confident`
  is additive, not a replacement for `_find_series`'s existing behavior
  used elsewhere.
- Manga support in `add-comic` — Comic Geeks is comics-focused; manga
  continues to go through the existing ISBN-based physical import path.
