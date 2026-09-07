# comic-view-ui

Scans folders of `.cbz`/`.cbr` comics and manga, pulls whatever metadata it
can find, and builds a single flattened `data/library.json` database — plus
a cover image and a few preview pages per comic for display. It also imports
physical comics/manga from a workbook of UPCs/ISBNs, merging into a digital
record when you own the same issue both ways. This is Phase 1/2: mapping the
collection. The explorable UI comes later, built on top of this data.

Original folder structure and file locations are **not** preserved or
referenced — everything is identified by a stable content hash, and once a
comic is scanned, the library no longer needs to know where the source file
lives.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Then, once, install a headless browser for Playwright:

```bash
playwright install chromium
```

This is required, not optional: League of Comic Geeks added a Cloudflare
managed challenge that blocks plain HTTP requests outright, so `add-comic`,
`check-pulls`, and the viewer's manual "paste a League of Comic Geeks
link" attach feature (see below) all fetch Comic Geeks pages through a
real headless browser instead. Skip this step and those features fail with
a generic "couldn't read that page" error and no clearer explanation.

CBR support shells out to a system unrar tool. On macOS:

```bash
brew install unar
```

Copy the config template and fill in your folders:

```bash
cp config.example.yaml config.yaml
```

```yaml
roots:
  - path: "~/Comics"
    type: comic
  - path: "~/Manga"
    type: manga
```

Each root is scanned recursively — nested folders (e.g. `Comics/Batman/`)
are searched too; everything found is flattened into one library regardless
of subfolder layout.

Optionally, add a shell alias so `add-comic <url>` (see below) works from
any directory, not just this checkout — add this line to your shell rc
(e.g. `~/.zshrc`):

```bash
alias add-comic="/path/to/comic-view-ui/bin/add-comic"
```

## Usage

Scan (no network calls, no credentials needed):

```bash
comic-library scan
```

Re-run `scan` any time you add new comics — it's incremental. Existing
entries (including `status`) are left untouched; only new files are added.

Enrich missing metadata via Metron and Google Books (optional, needs
credentials in `config.yaml` for Metron; Google Books works keyless at low
volume):

```bash
comic-library enrich
```

`enrich` only fills in fields that are still empty (including cover images
for physical-only comics — see below). Pass `--force` to re-query records
that already have complete data.

Import physical comics/manga from a single workbook with two sheets —
`Comics` and `Manga` (sheet names matched case-insensitively), each with
columns `Name` and `UPC/ISBN` — enriching each new row immediately (no
separate `enrich` run needed):

```bash
comic-library import-physical --file "/path/to/collection.xlsx"
```

A comics-sheet row is looked up on Metron by its UPC (`/issue/?upc=`),
falling back to an exact series+issue-number lookup if Metron's UPC index
doesn't have that specific code (a real, common gap), and finally to fuzzy
title+year search if no issue number could be parsed from the title. A
manga-sheet row is looked up on Open Library by its ISBN first, with Google
Books as a fallback for whatever Open Library doesn't have (mainly
`description`, which Open Library has no field for at all). A row whose
barcode Excel silently corrupted by rounding it to a float is detected and
skipped (reported in the command's output) rather than looked up wrong —
fix the source file (re-enter that column as Text) and re-run.

A row that resolves to a series + issue/volume number matching an already-
scanned digital record is merged into it — that record's `formats` becomes
`["digital", "print"]`, reusing the cover/preview pages already extracted
from the digital file. Everything else becomes a new record with
`formats: ["print"]`; print-only records have no local archive to extract a
cover from, so the fetched cover from Metron/Open Library/Google Books is
used instead, and `preview_pages` stays empty. Re-running `import-physical`
on an updated workbook is safe — a barcode already seen on a previous run
(whether it ended up merged or as its own record) is skipped without
hitting the network again.

Add a single comic straight from its League of Comic Geeks issue page —
digital by default, or physical with `--physical`:

```bash
add-comic "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16"
add-comic "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16" --physical
```

(`add-comic` is the shell alias set up above; without it, run
`comic-library add-comic <url>` from this checkout instead.) It resolves
to an existing record by UPC or by series+issue-number match, adding the
new format to it, or otherwise creates a new one. This is the manual
counterpart to `check-pulls` — use it for a one-off digital buy, or a
physical pickup outside your regular pull list.

Fetch your pull-list calendar and auto-add anything newly released
(optional, needs both Metron credentials and `pull_list.calendar_url` set
in `config.yaml` — see `config.example.yaml`, which points at where to
find your League of Comic Geeks pull-list ICS feed URL):

```bash
comic-library check-pulls
```

`check-pulls` resolves each new release via Metron and adds it as a
physical record (merging into a matching existing record — digital or
print — where possible), the same way `import-physical` does. An
ambiguous or unresolvable title is flagged in the command's output rather
than guessed at, for `add-comic` to sort out by hand. This command is
meant to be run by a scheduled routine, not typically invoked directly —
and it never touches git itself, so that routine can review its changes
before committing. It tracks which calendar events it's already processed
in `data/pull_state.json` (see below), so re-runs don't duplicate work.

Serve `viewer.html` + `data/` over HTTP, so the browser can actually fetch
`data/library.json` and cover images (opening `viewer.html` via `file://`
blocks those fetches):

```bash
comic-library serve --port 8000
```

Then open `http://127.0.0.1:8000/viewer.html`. Each card also has controls
to manually fix up a record that the automatic import couldn't resolve on
its own (a printing/variant Metron's UPC index doesn't have, or a record
still missing a cover):

- **Upload a cover image** directly — saved as-is, overwriting any
  existing cover.
- **Paste a League of Comic Geeks issue link** (e.g.
  `https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16`) —
  replaces series, issue number, publisher, year, description, author,
  cover, and `upc` (each printing/variant there has its own accurate
  barcode) with that issue's data. The record's `title` is left untouched,
  since it's what encodes printing/variant info (e.g. "2nd Printing")
  specific to the physical copy owned.

## Data

- `data/library.json` — the flattened database (gitignored — it's your
  personal collection)
- `data/covers/<id>/` — extracted cover + preview page images per comic
  (gitignored)
- `data/pull_state.json` — tracks which pull-list calendar events
  `check-pulls` has already processed, so re-runs don't duplicate work
  (git-tracked, like the library files, so state survives across
  machines/branches)

## Tests

```bash
pytest
```
