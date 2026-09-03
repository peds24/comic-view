# comic-view-ui

Scans folders of `.cbz`/`.cbr` comics and manga, pulls whatever metadata it
can find, and builds a single flattened `data/library.json` database — plus
a cover image and a few preview pages per comic for display. This is Phase
1: mapping the collection. The explorable UI comes later, built on top of
this data.

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

`enrich` only fills in fields that are still empty. Pass `--force` to
re-query records that already have complete data.

## Data

- `data/library.json` — the flattened database (gitignored — it's your
  personal collection)
- `data/covers/<id>/` — extracted cover + preview page images per comic
  (gitignored)

## Tests

```bash
pytest
```
