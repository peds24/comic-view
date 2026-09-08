# Web App Skeleton + Quick-Add — Design Spec

## Context

`2026-09-02-3d-browsing-ui-design.md` split the explorable UI into three
sub-projects: **A** (core 3D browsing shelf, read-only), **B** (local owner
backend + upload UI for growing the collection from the browser), and **C**
(public read-only snapshot). A was scoped first, with B explicitly deferred
until A was built and validated.

The user now wants to start both at once, in a different shape than
originally planned for B: instead of drag-and-drop file upload, adding a
comic/manga happens by typing an identifier — a UPC/ISBN/League of Comic
Geeks link for a comic, or a title/ISBN for manga — the same identifiers
already used by `comic-library import-physical` and the manual-attach
feature in `viewer.html`, just for a single new item instead of a batch
workbook or fixing up an existing record.

This spec covers a first pass of **both** pieces, structure only, no visual
styling:
- The sub-project A shelf/carousel skeleton, built as a working (not
  stubbed) component tree and data flow.
- A owner-only quick-add flow, living in the same app at a route nothing
  links to, so it's naturally excluded from whatever C eventually
  publishes.

## Architecture & data flow

A new `web/` directory holds a React + TypeScript + Vite app, independent of
the Python package's own toolchain, per the A spec. It has two views:

- **`/` — the browsing shelf** (sub-project A): reads `data/library.json`
  and `data/covers/**`. In dev, Vite proxies `/data/*` to the existing
  `comic-library serve` server; nothing here writes anything.
- **`/admin` — quick-add** (this spec's new piece): not linked from the
  shelf's nav or anywhere else. Submits to the same local server's new
  `/api/add-comic` / `/api/add-manga` routes.

`comic-library serve` (`library/viewer_server.py`) already runs a
local-only HTTP server (no auth — matches sub-project B's "local-only, no
public exposure" framing) exposing write routes for editing existing
records (attach cover, attach Comic Geeks link, edit title/year/formats,
delete). This spec adds two more routes to the same server for *creating*
records, rather than starting a second backend — there is exactly one
local owner-facing server, and the new React app's `/admin` route is a new
frontend for it, alongside the existing `viewer.html`, which is left
running as-is (its own edit-existing-record affordances stay put; nothing
here removes them).

```
web/
  index.html
  vite.config.ts          # dev server: serve ../data at /data, proxy /api to :8000
  package.json
  tsconfig.json
  src/
    main.tsx
    App.tsx                    # routes "/" -> shelf, "/admin" -> quick-add
    types/comic.ts             # ComicRecord mirror
    data/useLibrary.ts         # fetch + parse /data/library.json
    components/
      CoverShelf.tsx
      CoverCard.tsx
      DetailOverlay.tsx
      TimelineScrubber.tsx
      FilterBar.tsx
      admin/
        AddItemForm.tsx
    hooks/
      useScrollPhysics.ts
      useVirtualizedWindow.ts
    styles/
      shelf.css               # left empty/minimal this pass
```

## Part 1 — Shelf skeleton (sub-project A, structure only)

Same component breakdown, interactions, and behavior as
`2026-09-02-3d-browsing-ui-design.md` describes, built for real rather than
stubbed, with visual styling deferred:

- `CoverShelf`/`CoverCard`: real DOM structure and real focus-index state,
  positioned with plain (unstyled) elements instead of the
  `perspective`/`translate3d`/`rotateY` transform stack — the *mechanism*
  for what's focused and what's rendered is correct now; how it looks in 3D
  comes later.
- `useVirtualizedWindow`: renders only `currentIndex ± 6`, as spec'd.
- `useScrollPhysics`: real velocity tracking and snap-to-nearest-item, since
  that's behavior, not visuals.
- `DetailOverlay`: opens on click with the real record's cover, preview
  pages, description, publisher, year, status, and formats badge; unstyled
  layout (no side-by-side/stacked responsive treatment yet).
- `FilterBar`: working Year Published / A→Z / Z→A sort modes and a
  publisher single-select filter, composing as spec'd.
- `TimelineScrubber`: shows the sort-mode-appropriate value (year or
  letter) and updates on scroll; drag-to-jump is real if straightforward,
  otherwise a follow-up.
- Responsive breakpoints, touch-drag-as-primary-input on phone, and the
  Waxlog-style depth/recession look are explicitly deferred to the styling
  pass.

## Part 2 — Quick-add

### Backend: `library/quick_add.py`

A few of `physical_importer.py`'s helpers are promoted from private
(`_`-prefixed) to shared module-level functions, since quick-add needs the
exact same routing/enrichment logic for a single item that the batch
importer already has for a workbook row: `is_isbn_shaped`, `truncate_isbn`,
`enrich_comic_by_upc` (currently `_enrich_comic`), `enrich_isbn` (currently
`_enrich_isbn`). `physical_importer.py` keeps calling them under their new
names; no behavior changes there.

```python
def add_comic(
    records: dict[str, ComicRecord], raw_input: str, formats: list[str], *,
    metron: MetronSource | None, google_books: GoogleBooksSource,
    open_library: OpenLibrarySource, covers_dir: Path,
) -> AddResult: ...

def add_manga(
    records: dict[str, ComicRecord], raw_input: str, formats: list[str], *,
    google_books: GoogleBooksSource, open_library: OpenLibrarySource,
    covers_dir: Path,
) -> AddResult: ...
```

`AddResult` is a small dataclass: `record: ComicRecord`, `merged: bool`
(True if merged into an existing digital record, False if newly created).
Both functions raise `QuickAddError(str)` only when a record genuinely
can't be built: unrecognized input shape, or a Comic Geeks link that can't
be resolved (mirrors `LinkAttachError` today). A UPC/ISBN/title lookup that
comes back empty does **not** raise — like the batch importer's existing
tolerance (`_enrich_comic_by_title` fills nothing rather than erroring), a
bare record is still created from what the user typed, since "nothing
found yet" shouldn't block adding the item to the collection. The route
layer turns `QuickAddError` into a 422, same convention as
`manual_attach.LinkAttachError` today.

**`add_comic` routing** (checked in this order):
1. Input contains `leagueofcomicgeeks.com`, or is purely a bare numeric
   Comic Geeks id — actually a Comic Geeks id is indistinguishable from a
   UPC by shape alone, so: **only a string containing `http`/the domain**
   is treated as a link; a bare numeric string is always UPC/ISBN, never
   assumed to be a Comic Geeks id (this narrows `comic_geeks.fetch_issue`'s
   existing bare-id convenience to link-only for quick-add, where
   ambiguity with barcodes makes it unsafe to guess).
   Builds a fresh `ComicRecord(type="comic", formats=formats)` with a
   placeholder id, calls `manual_attach.attach_comic_geeks_issue`, then
   sets `title` from `f"{series} #{issue_number}"` (or just `series` if no
   issue number) since that function deliberately never sets title. Final
   id becomes `cg-<comic-geeks-id-parsed-from-the-url>`.
2. All-digit, starts with `9` → ISBN path: `id = f"isbn-{code}"`,
   `enrich_isbn(record, code, google_books, open_library, covers_dir)`.
3. All-digit, otherwise → UPC path: `id = f"upc-{code}"`,
   `enrich_comic_by_upc(record, code, metron, covers_dir)` (Metron, with
   its existing title-search fallback when the UPC isn't indexed).
4. Anything else → `QuickAddError("Comics need a UPC, ISBN, or a League of
   Comic Geeks link.")`.

After enrichment, if `series` + `issue_number` are present and
`is_matchable`, try `find_digital_match` exactly like the batch importer;
merge (append missing format(s), fill `isbn`/`upc` if empty) if found,
otherwise add as new with `formats` set to **what the user picked** — this
is the one behavioral difference from the batch path, which always hard-
codes `["print"]` since it only ever imports physical items. Quick-add
lets a Digital-only or Digital+Physical pick through, since this flow is
also for logging a digital purchase with no local file scanned yet.

**`add_manga` routing:**
1. All-digit → ISBN path, same as comics' ISBN path
   (`enrich_isbn`), `id = f"isbn-{code}"`.
2. Otherwise → treated as a title: `google_books.search(title)` +
   `google_books.cover_image_url(title)` (the same best-effort
   search-by-title approach `physical_importer._enrich_comic_by_title`
   already uses as a fallback, just against Google Books directly, since
   Metron has no manga coverage and Open Library has no free-text search
   client in this codebase). `id = f"manual-{slugify(title)}-{short_hash}"`
   (matching the existing `manual-<slug>` id convention already seen for
   other hand-entered records). If Google Books returns nothing at all,
   the record is still created from the typed title alone (better than
   failing quick-add outright — this mirrors "nothing found" tolerance in
   `_enrich_comic_by_title`, which fills nothing rather than erroring),
   with a note in the response that no metadata was found.

Same merge-into-digital-match behavior as comics.

### New routes on `ViewerRequestHandler`

- `POST /api/add-comic` — body `{input: str, formats: list[str]}`. Calls
  `quick_add.add_comic`, saves into `library_comics.json`, responds
  `{ok: true, merged: bool, record: {...}}` or `422 {error: str}`.
- `POST /api/add-manga` — same shape, saves into `library_manga.json`.

`formats` is validated the same way `_update_formats` already validates it
(non-empty list, only `"digital"`/`"print"` values).

### Frontend: `/admin` quick-add form

`AddItemForm.tsx`:
- Comic/Manga toggle (radio or two buttons).
- One text input; placeholder text changes with the toggle (e.g. "UPC,
  ISBN, or League of Comic Geeks link" vs. "Title or ISBN"). No
  client-side kind-detection — the server does all routing; the client
  just posts the raw string.
- Digital / Physical checkboxes — either or both may be checked; submit
  disabled until at least one is checked.
- On submit: POSTs to `/api/add-comic` or `/api/add-manga` based on the
  toggle, then shows the returned title + cover thumbnail and whether it
  was merged into an existing record, or the server's error message
  inline. Form stays populated on error so the user can correct and
  resubmit.

## Explicitly out of scope for this pass

- All visual styling/CSS (shelf 3D look, admin form layout) — a later
  pass, for both parts.
- Drag-and-drop file upload — superseded by the identifier-based flow for
  this project; batch `.xlsx` import stays CLI-only (`import-physical`).
- Sub-project C (public static-publish split) — the `/admin` route is
  simply unlinked; enforcing its exclusion from a published build is C's
  problem when that sub-project is built.
- Any change to `scan`, `enrich`, `fetch-covers`, or other existing CLI
  commands.
- Auth on the new routes — same no-auth, local-only posture as the
  existing write routes.

## Verification plan

- **Python**: unit tests for `quick_add.add_comic`/`add_manga` in
  `tests/test_quick_add.py`, mocking `MetronSource`/`GoogleBooksSource`/
  `OpenLibrarySource`/`comic_geeks.fetch_issue` — covering all four input
  kinds (UPC, ISBN, Comic Geeks link, manga title), merge-into-existing
  vs. new-record for each, the "nothing found" tolerant paths, and the
  rejected-input case. Follows the existing patterns in
  `tests/test_physical_importer.py` and `tests/test_manual_attach.py`.
- **Vitest** for the shelf's pure logic (scroll-physics math, virtualization
  window calc, sort/filter functions), per the A spec.
- **Manual verification in headless Chrome via Playwright** (per standing
  instruction): run `comic-library serve` alongside `npm run dev`; on the
  shelf, confirm scroll/click/sort/filter/timeline all work against the
  real library data; on `/admin`, exercise all four quick-add input kinds
  end-to-end against real network sources (or a temp/sandboxed
  `config.yaml` if credentials are a concern) and confirm the new/merged
  record shows up back on the shelf.
