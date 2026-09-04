# Comics/manga library split — design

## Background

The library JSON database has fragmented across three files during recent
development:

- `data/library.json` (115 records) — the original single-file database,
  now stale. All physical-import output (`isbn-`/`upc-` prefixed ids), plus
  29 records that were merged with a digital scan back when `scan` still
  wrote here directly.
- `data/library_digital.json` (347 records) — current `scan` output
  (content-hash ids). Diverged from `library.json` once `scan` moved to
  writing here instead (see `--data` default added to the `scan` command).
- `data/library_first_merge.json` (448 records) — a prior attempt at
  reconciling the two above. The user has since been actively editing this
  file through the viewer (attaching Comic Geeks links to comics records),
  making it the most up-to-date source for comics data specifically,
  despite some known issues in how it was produced (see below).

None of these three files separate comics from manga — every command and
the viewer currently work against one mixed file.

## Goal

Replace the three-file tangle with exactly two canonical files, split by
`type`, each holding every format (digital-only, print-only, or both) for
that type:

- `data/library_comics.json`
- `data/library_manga.json`

`scan`, `enrich`, `fetch-covers`, `import-physical`, and `serve` all target
these two files going forward; `library.json`, `library_digital.json`, and
`library_first_merge.json` are retired.

## Decisions already made (with the user, in conversation)

- **Source of truth for the split: `data/library_first_merge.json` as it
  stands today**, not a fresh re-merge of `library.json` +
  `library_digital.json`. The user is aware this file's merge pass was
  more aggressive than ideal (e.g. it merged "Monster: The Perfect
  Edition" (physical) into "Monster" (digital) — different-edition cases
  the user wants kept as separate records — and in doing so dropped the
  original digital record's real extracted cover in favor of a
  web-fetched one for at least that case) and will amend those specific
  records manually later. **This work does not attempt to fix or re-merge
  anything — it only splits the file that exists today by `type`.**
- **The split is permanent, everywhere** — not a one-off export. `scan`,
  `enrich`, `fetch-covers`, `import-physical`, and `serve` are all updated
  to work against the two type-split files instead of one mixed file.
- **The viewer stays a single page with tabs** (already built and
  verified this session) — not two separate HTML pages. `viewer_server.py`
  merges both files server-side for `GET /data/library.json`, so
  `viewer.html` needs no changes at all.
- **Must be reversible.** `data/` isn't in git today. Before any split
  happens: the three existing files are committed to `main` as a baseline
  (small, ~600KB total — cheap insurance), and the actual split work
  happens on an isolated git worktree/branch, not in the working directory
  in place. `data/covers/` and `*.csv`/`*.xlsx` exports stay gitignored —
  only the JSON library files are tracked.

## What "split by type" means concretely

Read `data/library_first_merge.json`, partition its 448 records by
`record.type` (`"comic"` or `"manga"`), write:

- `data/library_comics.json` — the 249 `type: "comic"` records
- `data/library_manga.json` — the 199 `type: "manga"` records

No merging, deduplication, or field changes — a straight partition. Record
ids, cover paths, formats, and metadata all carry over untouched.

This is a one-time script, not a permanent CLI command (nothing else in
the app needs to re-split a file after this).

## Code changes

**`store.py`** — no change. It's already just "load/save a dict of
records from a path"; only callers need to know about two paths.

**`cli.py`**:
- `scan`: currently writes all found records (both types) to one
  `--data`-named file. Changes to load/save two files
  (`library_comics.json` / `library_manga.json`, or whatever `--data-*`
  flags are added), routing each found record by `record.type` (already
  known from `config.roots`).
- `enrich` / `fetch-covers`: currently operate on one `library.json`.
  Changes to run once per file (loop over the two paths). This actually
  simplifies the existing type-based source routing in
  `_ordered_cover_sources` — once a file only ever contains one type, that
  branch becomes a safety net instead of load-bearing logic.
- `import-physical`: currently loads/saves one `library.json`. Splits
  naturally, since the workbook already has separate "Comics" and "Manga"
  sheets — each sheet's rows just go to their own file's dict instead of
  a shared one.
- `serve`: currently takes one `--data` filename. Takes two paths instead
  (sensible defaults: `library_comics.json` / `library_manga.json`).

**`viewer_server.py`**:
- Constructor takes `comics_path` + `manga_path` instead of one
  `library_path`.
- `GET /data/library.json`: loads both files, concatenates their record
  arrays, serves the combined JSON. `viewer.html`'s single fetch and
  client-side tab filtering keep working unchanged.
- POST routes (`attach-cover`, `attach-link`, `update-title`,
  `update-year`, `update-formats`, `delete-record`): look up which of the
  two loaded dicts actually contains the given record id, mutate and save
  only that file.

**`.gitignore`**: un-ignore `data/library_comics.json` and
`data/library_manga.json` (the new live files) plus the three existing
files as the baseline-commit snapshot. `data/covers/`, `data/*.csv`,
`data/*.xlsx` stay ignored.

**Migration**: a throwaway script (not kept in the repo afterward) that
does the partition described above, run once inside the worktree.

## Safety / rollback plan

1. On `main`, in place (no worktree needed for this step — it's purely
   additive): un-ignore and commit `library.json`, `library_digital.json`,
   and `library_first_merge.json` as they exist right now. This alone is
   a restore point even before anything else happens.
2. Open a git worktree on a new branch. All remaining work — the split
   script, the code changes above, and the resulting
   `library_comics.json` / `library_manga.json` — happens there.
3. Verify in the worktree: run the full test suite, and smoke-test
   `serve` against the split files (confirm the viewer renders identically
   to today, tabs and all, confirm attach/update/delete round-trip to the
   correct file).
4. Old files (`library.json`, `library_digital.json`,
   `library_first_merge.json`) are renamed (e.g. `.pre-split.json`
   suffix) rather than deleted, so there's a filesystem-level undo too,
   independent of git.
5. Merge the branch back to `main` only after the user reviews.

## Out of scope (explicitly)

- Fixing the "Monster: The Perfect Edition" / "Vagabond (VIZBIG)" /
  Gundam edition-merge issues in `library_first_merge.json`'s history —
  user will amend these manually later.
- The manga per-volume description enrichment work (Open Library /
  Google Books ISBN resolution) discussed earlier in this session — that
  is a separate follow-up, unblocked by this split but not part of it.
- Re-deriving why `library.json` and `library_digital.json` diverged
  beyond what's needed to write this doc (already understood via git
  history: `scan`'s `--data` default changed to `library_digital.json`
  partway through development, and the old file was never reconciled
  until the `library_first_merge.json` attempt).
