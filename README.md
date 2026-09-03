# comic-view-ui

Scans folders of `.cbz`/`.cbr` comics and manga, pulls whatever metadata it
can find, and builds a single flattened `data/library.json` database — plus
a cover image and a few preview pages per comic for display. It also imports
physical comics from a Comic Geeks Excel export and physical manga from an
ISBN barcode-scan CSV, merging into a digital record when you own the same
issue both ways. This is Phase 1/2: mapping the collection. The explorable
UI comes later, built on top of this data.

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

Import physical comics from a Comic Geeks Excel export (no network calls):

```bash
comic-library import-physical --file "/path/to/ComicGeeks-export.xlsx"
```

Only rows with "In Collection" checked are imported. A physical comic that
matches an existing digital record (same series + issue number) is merged
into it — that record's `formats` becomes `["digital", "physical"]`, reusing
the cover/preview pages already extracted from the digital file. Everything
else becomes a new record with `formats: ["physical"]`. Collected editions,
annuals, and variant printings are never auto-matched against a single-issue
digital record — they always become their own physical-only entry.

Physical-only records have no local archive to extract a cover from, so
`comic-library enrich` fetches one from Metron/Google Books instead (this
needs at least one of those configured in `config.yaml` — see below).
`preview_pages` stays empty for physical-only records; legitimate metadata
sources expose a cover image, not interior page scans. Re-running
`import-physical` on an updated export is safe — already-merged and
already-imported entries aren't duplicated.

Import physical manga from a barcode-scanner CSV export (ISBNs only —
**this one requires network access**, since a bare barcode has no other way
to be identified):

```bash
comic-library import-manga-isbn --file "/path/to/scanned-codes.csv"
```

Needs `google_books.api_key` set in `config.yaml`. Each row is looked up on
Google Books by ISBN for title/author/publisher/year/description and a
cover (falling back to a title search if the exact edition has no cover
image); rows that aren't a valid ISBN-13 (e.g. a supplementary price barcode
scanned by mistake) are skipped and reported. Matching against existing
digital manga works the same way as `import-physical` — same series +
volume merges into one record, collected/variant editions (Omnibus, VIZBIG,
Perfect Edition, etc.) always become their own physical-only entry.
`status` defaults to `unread`, since barcode scans carry no read/unread
signal. Idempotent — re-running on an updated export doesn't duplicate
already-imported ISBNs.

## Data

- `data/library.json` — the flattened database (gitignored — it's your
  personal collection)
- `data/covers/<id>/` — extracted cover + preview page images per comic
  (gitignored)

## Tests

```bash
pytest
```
