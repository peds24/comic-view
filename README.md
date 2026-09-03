# comic-view-ui

Scans folders of `.cbz`/`.cbr` comics and manga, pulls whatever metadata it
can find, and builds a single flattened `data/library.json` database — plus
a cover image and a few preview pages per comic for display. It also imports
physical comics from a Comic Geeks Excel export, merging into a digital
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
into it — that record's `formats` becomes `["digital", "print"]`, reusing
the cover/preview pages already extracted from the digital file. Everything
else becomes a new record with `formats: ["print"]`. Collected editions,
annuals, and variant printings are never auto-matched against a single-issue
digital record — they always become their own print-only entry.

Print-only records have no local archive to extract a cover from, so
`comic-library enrich` fetches one from Metron/Google Books instead (this
needs at least one of those configured in `config.yaml` — see below).
`preview_pages` stays empty for print-only records; legitimate metadata
sources expose a cover image, not interior page scans. Re-running
`import-physical` on an updated export is safe — already-merged and
already-imported entries aren't duplicated.

Import comics and/or manga from a Comic Geeks export directly into an
enriched library, in one pass (no separate `enrich` run needed) — routes
each row to a metadata source by its own barcode:

```bash
comic-library import-comic-geeks --comics "/path/to/comics-export.xlsx" --manga "/path/to/manga-export.xlsx"
```

Both flags are optional but at least one is required. Per row: a 17-digit
Diamond UPC goes to Metron's exact `/issue/?upc=` lookup (falling back to
an exact series+issue-number lookup if Metron's UPC index doesn't have that
specific code — a real, common gap); a 13-digit ISBN (978/979 prefix) goes
to Open Library first, Google Books as fallback for whatever Open Library
doesn't have (mainly `description`); a row with no usable code falls back
to an exact series+issue-number Metron lookup when an issue number is
known, otherwise fuzzy title+year search as a last resort. A cell Excel
silently corrupted by rounding a long UPC to a float is detected and
skipped (reported in the command's output) rather than looked up wrong —
fix the source file (re-enter that column as Text) and re-run; already-
imported rows aren't duplicated. `formats` is always `["print"]`; `status`
comes from the export's "Marked Read" column.

Serve `viewer.html` + `data/` over HTTP, so the browser can actually fetch
`data/library.json` and cover images (opening `viewer.html` via `file://`
blocks those fetches):

```bash
comic-library serve --port 8000
```

Then open `http://127.0.0.1:8000/viewer.html`.

## Data

- `data/library.json` — the flattened database (gitignored — it's your
  personal collection)
- `data/covers/<id>/` — extracted cover + preview page images per comic
  (gitignored)

## Tests

```bash
pytest
```
