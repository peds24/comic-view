# Quick-Add Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the owner add a single new comic or manga to the collection by typing an identifier (UPC/ISBN/Comic Geeks link for comics, title/ISBN for manga) and picking Digital/Physical/Both, from an owner-only `/admin` page — no drag-and-drop, no CLI.

**Architecture:** A new `library/quick_add.py` module reuses (via promotion from private to shared) the routing/enrichment logic already in `physical_importer.py`, exposing `add_comic`/`add_manga` for a single item instead of a workbook row. Two new POST routes on the existing `comic-library serve` server (`library/viewer_server.py`) call those functions and save to the appropriate library file. The `web/` app's `/admin` route (scaffolded as a placeholder in the prior shelf-skeleton plan) gets a real form that posts to those routes.

**Tech Stack:** Python (existing `library/` package, `pytest`), the `web/` Vite React+TS app from the prior plan.

**Spec:** `docs/superpowers/specs/2026-09-04-web-app-and-quick-add-design.md` (Part 2).

**Depends on:** `docs/superpowers/plans/2026-09-04-web-app-shelf-skeleton.md` (Task 10 leaves an `AdminPlaceholder` component in `web/src/App.tsx` that Task 6 here replaces).

## Global Constraints

- No visual styling this pass — the admin form is plain unstyled markup.
- No auth on the new routes — same local-only posture as the existing write routes in `viewer_server.py`.
- `formats` sent from the client must be validated exactly like `_update_formats` already validates it: non-empty list, values restricted to `"digital"`/`"print"`.
- A lookup that finds nothing still creates a bare record from what the user typed — only truly unusable input (unrecognized shape, or an unreadable Comic Geeks link) is rejected with an error.
- No changes to `scan`, `enrich`, `fetch-covers`, or other existing CLI commands.

---

### Task 1: Promote `physical_importer.py`'s private routing helpers to shared functions

**Files:**
- Modify: `library/physical_importer.py`
- Test: `tests/test_physical_importer.py` (no test changes needed — this is a pure rename; existing tests must keep passing as the regression check)

**Interfaces:**
- Produces (renamed, now public): `is_isbn_shaped(code: str) -> bool` (was `_is_isbn_shaped`); `truncate_isbn(code: str) -> str` (was `_truncate_isbn`); `enrich_comic_by_upc(record, upc, metron, covers_dir) -> None` (was `_enrich_comic`); `enrich_isbn(record, isbn, google_books, open_library, covers_dir) -> None` (was `_enrich_isbn`). Signatures are unchanged, only the names lose their leading underscore.

- [ ] **Step 1: Rename the four functions and their call sites within the file**

In `library/physical_importer.py`:
- Rename `_is_isbn_shaped` → `is_isbn_shaped`, and its one call site inside `_import_comic_row`.
- Rename `_truncate_isbn` → `truncate_isbn`, and its two call sites (`_import_comic_row`, `_import_manga_row`).
- Rename `_enrich_comic` → `enrich_comic_by_upc`, and its one call site inside `_import_comic_row`.
- Rename `_enrich_isbn` → `enrich_isbn`, and its two call sites (`_import_comic_row`, `_import_manga_row`).

Leave `_enrich_comic_by_title`, `_apply_metron_issue`, `_fill_missing`, `_find_sheet`, `_load_rows`, `_normalize_code`, `_import_comic_row`, `_import_manga_row` as private — they're either xlsx-row-shaped or only used by the two functions above.

- [ ] **Step 2: Run the existing test suite to confirm nothing broke**

```bash
pytest tests/test_physical_importer.py -v
```

Expected: all 11 tests still PASS (pure rename, no behavior change).

- [ ] **Step 3: Commit**

```bash
git add library/physical_importer.py
git commit -m "Promote ISBN/UPC routing helpers to shared functions for reuse by quick-add"
```

---

### Task 2: `quick_add.py` — Comic Geeks link path

**Files:**
- Create: `library/quick_add.py`
- Test: `tests/test_quick_add.py`

**Interfaces:**
- Consumes: `manual_attach.attach_comic_geeks_issue`, `manual_attach.LinkAttachError` (existing); `matching.find_digital_match`, `matching.is_matchable` (existing); `models.ComicRecord` (existing).
- Produces: `class QuickAddError(Exception)`; `@dataclass class AddResult: record: ComicRecord; merged: bool`; `add_comic(records: dict[str, ComicRecord], raw_input: str, formats: list[str], *, metron, google_books, open_library, covers_dir: Path) -> AddResult` (this task implements only the Comic Geeks link branch; Task 3 adds UPC/ISBN).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_quick_add.py
from pathlib import Path

import pytest

from library.manual_attach import LinkAttachError
from library.models import ComicRecord
from library.quick_add import AddResult, QuickAddError, add_comic


class FakeCoverResponse:
    content = b"fake-cover-bytes"

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _fake_cover_download(monkeypatch):
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())


def test_add_comic_from_comic_geeks_link_creates_new_record(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {
        "series": "Absolute Batman", "issue_number": "16", "publisher": "DC Comics", "year": 2026,
        "description": "A synopsis.", "author": "Scott Snyder", "upc": "76194138584601611",
        "_image_url": "https://example.com/cover.jpg",
    })
    records: dict[str, ComicRecord] = {}

    result = add_comic(
        records, "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", ["print"],
        metron=None, google_books=None, open_library=None, covers_dir=tmp_path,
    )

    assert isinstance(result, AddResult)
    assert result.merged is False
    assert result.record.type == "comic"
    assert result.record.title == "Absolute Batman #16"
    assert result.record.series == "Absolute Batman"
    assert result.record.publisher == "DC Comics"
    assert result.record.formats == ["print"]
    assert result.record.upc == "76194138584601611"
    assert result.record.id in records
    assert records[result.record.id] is result.record


def test_add_comic_from_comic_geeks_link_sets_title_to_series_only_when_no_issue_number(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {"series": "Some TPB"})
    records: dict[str, ComicRecord] = {}

    result = add_comic(
        records, "https://leagueofcomicgeeks.com/comic/1/some-tpb", ["digital"],
        metron=None, google_books=None, open_library=None, covers_dir=tmp_path,
    )

    assert result.record.title == "Some TPB"


def test_add_comic_from_comic_geeks_link_merges_into_existing_digital_record(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {
        "series": "Absolute Batman", "issue_number": "16",
    })
    records: dict[str, ComicRecord] = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="16", formats=["digital"],
        )
    }

    result = add_comic(
        records, "https://leagueofcomicgeeks.com/comic/1/absolute-batman-16", ["print"],
        metron=None, google_books=None, open_library=None, covers_dir=tmp_path,
    )

    assert result.merged is True
    assert result.record is records["d1"]
    assert records["d1"].formats == ["digital", "print"]
    assert len(records) == 1


def test_add_comic_from_unreadable_comic_geeks_link_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.fetch_issue", lambda url: {})
    records: dict[str, ComicRecord] = {}

    with pytest.raises(QuickAddError):
        add_comic(
            records, "https://leagueofcomicgeeks.com/comic/999/nope", ["print"],
            metron=None, google_books=None, open_library=None, covers_dir=tmp_path,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_quick_add.py -v
```

Expected: FAIL — `library.quick_add` doesn't exist yet.

- [ ] **Step 3: Implement `quick_add.py` (Comic Geeks branch only)**

```python
# library/quick_add.py
"""Add a single new comic or manga to the collection from an identifier the
owner already has in hand — a UPC/ISBN/League of Comic Geeks link for a
comic, or a title/ISBN for manga — rather than a batch workbook
(`physical_importer.py`) or a local scanned file (`scanner.py`). Powers the
`/api/add-comic` and `/api/add-manga` routes `comic-library serve` exposes
to the web app's owner-only quick-add form.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from library.manual_attach import LinkAttachError, attach_comic_geeks_issue
from library.matching import find_digital_match, is_matchable
from library.metadata_sources import comic_geeks
from library.models import ComicRecord


class QuickAddError(Exception):
    """Raised when a record genuinely can't be built from the given input:
    an unrecognized input shape, or an unreadable Comic Geeks link. A
    lookup that simply finds nothing does NOT raise — a bare record is
    still created from what the user typed, same tolerance as the batch
    importer's title-search fallback."""


@dataclass
class AddResult:
    record: ComicRecord
    merged: bool


def _merge_or_add(records: dict[str, ComicRecord], record: ComicRecord, code_field: str | None, code: str | None) -> AddResult:
    match = None
    if record.series and record.issue_number and is_matchable(record.title, record.issue_number):
        match = find_digital_match(records, record.series, record.issue_number)

    if match is not None:
        for fmt in record.formats:
            if fmt not in match.formats:
                match.formats.append(fmt)
        if code_field and code and not getattr(match, code_field, None):
            setattr(match, code_field, code)
        return AddResult(record=match, merged=True)

    records[record.id] = record
    return AddResult(record=record, merged=False)


_COMIC_GEEKS_ID_RE = re.compile(r"/comic/(\d+)")


def _comic_geeks_id_from_url(url: str) -> str:
    """Pulls the numeric issue id out of a full issue URL
    (`.../comic/6297209/absolute-batman-16` -> `"6297209"`), or returns the
    url unchanged if it's already a bare id — mirrors what
    `comic_geeks.fetch_issue` itself accepts, without reaching into that
    module's private `_resolve_url` helper."""
    match = _COMIC_GEEKS_ID_RE.search(url)
    return match.group(1) if match else url.strip()


def _add_comic_from_comic_geeks_link(records: dict[str, ComicRecord], url: str, formats: list[str], covers_dir: Path) -> AddResult:
    record = ComicRecord(id="pending", title="", type="comic", formats=list(formats))
    try:
        attach_comic_geeks_issue(record, url, covers_dir)
    except LinkAttachError as e:
        raise QuickAddError(str(e)) from e

    record.title = f"{record.series} #{record.issue_number}" if record.issue_number else (record.series or "")
    record.id = f"cg-{_comic_geeks_id_from_url(url)}"

    return _merge_or_add(records, record, "upc", record.upc)


def add_comic(
    records: dict[str, ComicRecord], raw_input: str, formats: list[str], *,
    metron, google_books, open_library, covers_dir: Path,
) -> AddResult:
    raw_input = raw_input.strip()

    if comic_geeks.is_comic_geeks_url(raw_input):
        return _add_comic_from_comic_geeks_link(records, raw_input, formats, covers_dir)

    raise QuickAddError("Comics need a UPC, ISBN, or a League of Comic Geeks link.")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_quick_add.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add library/quick_add.py tests/test_quick_add.py
git commit -m "Add quick_add.add_comic Comic Geeks link path"
```

---

### Task 3: `add_comic` — UPC and ISBN paths

**Files:**
- Modify: `library/quick_add.py`
- Test: `tests/test_quick_add.py`

**Interfaces:**
- Consumes: `physical_importer.is_isbn_shaped`, `physical_importer.truncate_isbn`, `physical_importer.enrich_comic_by_upc`, `physical_importer.enrich_isbn` (Task 1).
- Produces: `add_comic` now also handles all-digit input.

- [ ] **Step 1: Write the failing tests**

```python
# appended to tests/test_quick_add.py

from tests.test_physical_importer import FakeGoogleBooks, FakeMetron, FakeOpenLibrary


def test_add_comic_from_upc_routes_to_metron(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(upc_result={
        "series": {"name": "Absolute Batman"}, "number": "10",
        "desc": "A synopsis.", "credits": [],
    })

    result = add_comic(
        records, "76194138584601011", ["print"],
        metron=metron, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert metron.upc_calls == ["76194138584601011"]
    assert result.record.id == "upc-76194138584601011"
    assert result.record.upc == "76194138584601011"
    assert result.record.description == "A synopsis."
    assert result.record.formats == ["print"]


def test_add_comic_from_isbn_shaped_code_routes_to_open_library(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    open_library = FakeOpenLibrary(isbn_result={"author": "Frank Miller"})

    result = add_comic(
        records, "9781401207526", ["digital", "print"],
        metron=None, google_books=FakeGoogleBooks(), open_library=open_library, covers_dir=tmp_path,
    )

    assert result.record.id == "isbn-9781401207526"
    assert result.record.isbn == "9781401207526"
    assert result.record.author == "Frank Miller"
    assert result.record.formats == ["digital", "print"]


def test_add_comic_from_upc_with_no_metron_match_still_creates_bare_record(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    metron = FakeMetron(upc_result=None, search_result={})

    result = add_comic(
        records, "76194138584601011", ["print"],
        metron=metron, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.merged is False
    assert result.record.id == "upc-76194138584601011"
    assert result.record.title == "76194138584601011"


def test_add_comic_from_upc_merges_into_existing_digital_record(tmp_path: Path):
    records: dict[str, ComicRecord] = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="10", formats=["digital"],
        )
    }
    metron = FakeMetron(upc_result={"series": {"name": "Absolute Batman"}, "number": "10", "credits": []})

    result = add_comic(
        records, "76194138584601011", ["print"],
        metron=metron, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.merged is True
    assert records["d1"].formats == ["digital", "print"]
    assert records["d1"].upc == "76194138584601011"
    assert "upc-76194138584601011" not in records


def test_add_comic_rejects_unrecognized_input(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    with pytest.raises(QuickAddError):
        add_comic(
            records, "not a valid identifier", ["print"],
            metron=None, google_books=FakeGoogleBooks(), open_library=FakeOpenLibrary(), covers_dir=tmp_path,
        )
```

Note: the UPC-with-no-match test asserts `record.title == "76194138584601011"` — since a bare UPC lookup has no title source at all (unlike the batch importer, which gets the sheet's `Name` column), quick-add falls back to the raw code as a placeholder title so the record is never titled with an empty string. This behavior is implemented in Step 2 below.

- [ ] **Step 2: Implement the UPC/ISBN branches**

Replace the body of `add_comic` in `library/quick_add.py`:

```python
from library.physical_importer import enrich_comic_by_upc, enrich_isbn, is_isbn_shaped, truncate_isbn


def _add_comic_from_code(records: dict[str, ComicRecord], code: str, formats: list[str], *, metron, google_books, open_library, covers_dir: Path) -> AddResult:
    is_isbn = is_isbn_shaped(code)
    if is_isbn:
        code = truncate_isbn(code)

    record = ComicRecord(
        id=f"{'isbn' if is_isbn else 'upc'}-{code}", title=code, type="comic", formats=list(formats),
        **({"isbn": code} if is_isbn else {"upc": code}),
    )
    if is_isbn:
        enrich_isbn(record, code, google_books, open_library, covers_dir)
    else:
        enrich_comic_by_upc(record, code, metron, covers_dir)

    if record.series and record.issue_number:
        record.title = f"{record.series} #{record.issue_number}"

    code_field = "isbn" if is_isbn else "upc"
    return _merge_or_add(records, record, code_field, code)


def add_comic(
    records: dict[str, ComicRecord], raw_input: str, formats: list[str], *,
    metron, google_books, open_library, covers_dir: Path,
) -> AddResult:
    raw_input = raw_input.strip()

    if comic_geeks.is_comic_geeks_url(raw_input):
        return _add_comic_from_comic_geeks_link(records, raw_input, formats, covers_dir)

    if raw_input.isdigit():
        return _add_comic_from_code(
            records, raw_input, formats,
            metron=metron, google_books=google_books, open_library=open_library, covers_dir=covers_dir,
        )

    raise QuickAddError("Comics need a UPC, ISBN, or a League of Comic Geeks link.")
```

Add the new import line (`from library.physical_importer import ...`) near the top of `library/quick_add.py`, alongside the existing imports.

- [ ] **Step 3: Run tests to verify they pass**

```bash
pytest tests/test_quick_add.py -v
```

Expected: PASS (9 tests total)

- [ ] **Step 4: Commit**

```bash
git add library/quick_add.py tests/test_quick_add.py
git commit -m "Add quick_add.add_comic UPC/ISBN paths"
```

---

### Task 4: `add_manga`

**Files:**
- Modify: `library/quick_add.py`
- Test: `tests/test_quick_add.py`

**Interfaces:**
- Consumes: `physical_importer.enrich_isbn`, `physical_importer.truncate_isbn` (Task 1); `matching.strip_manga_volume_suffix`, `matching.extract_manga_issue`, `matching.find_digital_match` (existing).
- Produces: `add_manga(records: dict[str, ComicRecord], raw_input: str, formats: list[str], *, google_books, open_library, covers_dir: Path) -> AddResult`.

- [ ] **Step 1: Write the failing tests**

```python
# appended to tests/test_quick_add.py
from library.quick_add import add_manga


def test_add_manga_from_isbn_routes_to_open_library(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    open_library = FakeOpenLibrary(isbn_result={"author": "Hajime Isayama"})

    result = add_manga(
        records, "9781632368287", ["print"],
        google_books=FakeGoogleBooks(), open_library=open_library, covers_dir=tmp_path,
    )

    assert result.record.id == "isbn-9781632368287"
    assert result.record.isbn == "9781632368287"
    assert result.record.type == "manga"
    assert result.record.author == "Hajime Isayama"


def test_add_manga_from_title_searches_google_books(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    google_books = FakeGoogleBooks()
    google_books.search_result = {"author": "Hajime Isayama", "description": "Titans."}
    google_books.cover_result = "https://example.com/cover.jpg"

    result = add_manga(
        records, "Attack on Titan, Vol. 29", ["digital"],
        google_books=google_books, open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.record.type == "manga"
    assert result.record.title == "Attack on Titan, Vol. 29"
    assert result.record.series == "Attack on Titan"
    assert result.record.issue_number == "29"
    assert result.record.author == "Hajime Isayama"
    assert result.record.description == "Titans."
    assert result.record.id.startswith("manual-attack-on-titan-vol-29-")


def test_add_manga_from_title_with_no_search_results_still_creates_bare_record(tmp_path: Path):
    records: dict[str, ComicRecord] = {}
    google_books = FakeGoogleBooks()

    result = add_manga(
        records, "Some Obscure Title", ["print"],
        google_books=google_books, open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.merged is False
    assert result.record.title == "Some Obscure Title"
    assert result.record.author is None


def test_add_manga_from_title_merges_into_existing_digital_record(tmp_path: Path):
    """Merging needs a series + issue number to match against — a bare ISBN
    has no title text to derive those from (`enrich_isbn`, like the batch
    importer, never fills series/issue_number, only author/publisher/year/
    description), so only the title path can ever merge. This is a real
    limitation of ISBN-only quick-add input, not an oversight: if the owner
    wants a merge, typing the title (or fixing it up afterward in
    viewer.html) is the way."""
    records: dict[str, ComicRecord] = {
        "d1": ComicRecord(
            id="d1", title="Attack on Titan, Vol. 29", type="manga", series="Attack on Titan",
            issue_number="29", formats=["digital"],
        )
    }
    google_books = FakeGoogleBooks()
    google_books.search_result = {"author": "Hajime Isayama"}

    result = add_manga(
        records, "Attack on Titan, Vol. 29", ["print"],
        google_books=google_books, open_library=FakeOpenLibrary(), covers_dir=tmp_path,
    )

    assert result.merged is True
    assert result.record is records["d1"]
    assert records["d1"].formats == ["digital", "print"]
    assert len(records) == 1


def test_add_manga_from_bare_isbn_never_merges_since_no_title_to_match_on(tmp_path: Path):
    records: dict[str, ComicRecord] = {
        "d1": ComicRecord(
            id="d1", title="Attack on Titan, Vol. 29", type="manga", series="Attack on Titan",
            issue_number="29", formats=["digital"],
        )
    }
    open_library = FakeOpenLibrary(isbn_result={"author": "Hajime Isayama"})

    result = add_manga(
        records, "9781632368287", ["print"],
        google_books=FakeGoogleBooks(), open_library=open_library, covers_dir=tmp_path,
    )

    assert result.merged is False
    assert records["d1"].formats == ["digital"]  # untouched
    assert records["isbn-9781632368287"].isbn == "9781632368287"
```

`FakeGoogleBooks` in `tests/test_physical_importer.py` only implements `lookup_isbn`; extend it there (Step 2 below) so it also supports `search`/`cover_image_url`, matching the real `GoogleBooksSource` interface `add_manga`'s title path needs.

- [ ] **Step 2: Extend `FakeGoogleBooks` with `search`/`cover_image_url`**

In `tests/test_physical_importer.py`, replace the `FakeGoogleBooks` class:

```python
class FakeGoogleBooks:
    def __init__(self, isbn_result=None, search_result=None, cover_result=None):
        self.isbn_result = isbn_result or {}
        self.search_result = search_result or {}
        self.cover_result = cover_result
        self.calls = []
        self.search_calls = []

    def lookup_isbn(self, isbn):
        self.calls.append(isbn)
        return self.isbn_result

    def search(self, title, year=None):
        self.search_calls.append(title)
        return self.search_result

    def cover_image_url(self, title, year=None):
        return self.cover_result
```

Run `pytest tests/test_physical_importer.py -v` to confirm this extension doesn't break its existing tests (it only adds optional constructor args and two new methods; PASS expected, 11 tests).

- [ ] **Step 3: Run the new `add_manga` tests to verify they fail**

```bash
pytest tests/test_quick_add.py -v -k add_manga
```

Expected: FAIL — `add_manga` doesn't exist yet.

- [ ] **Step 4: Implement `add_manga`**

Add to `library/quick_add.py`, alongside new imports (`re` is already imported from Task 2):

```python
import hashlib

from library.matching import extract_manga_issue, strip_manga_volume_suffix
```

```python
def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled"


def add_manga(
    records: dict[str, ComicRecord], raw_input: str, formats: list[str], *,
    google_books, open_library, covers_dir: Path,
) -> AddResult:
    raw_input = raw_input.strip()

    if raw_input.isdigit():
        code = truncate_isbn(raw_input)
        record = ComicRecord(id=f"isbn-{code}", title=code, type="manga", isbn=code, formats=list(formats))
        enrich_isbn(record, code, google_books, open_library, covers_dir)
        code_field, code_value = "isbn", code
    else:
        title = raw_input
        issue_number = extract_manga_issue(title)
        record = ComicRecord(
            id=f"manual-{_slugify(title)}-{hashlib.sha1(title.encode()).hexdigest()[:8]}",
            title=title, type="manga",
            series=strip_manga_volume_suffix(title) if issue_number else None,
            issue_number=issue_number, formats=list(formats),
        )
        partial = google_books.search(title)
        for field, value in partial.items():
            if value:
                setattr(record, field, value)
                record.metadata_source[field] = "google_books"
        cover_url = google_books.cover_image_url(title)
        if cover_url:
            from library.covers import download_cover
            download_cover(record, cover_url, "google_books", covers_dir)
        code_field, code_value = None, None

    return _merge_or_add(records, record, code_field, code_value)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_quick_add.py -v
```

Expected: PASS (14 tests total)

- [ ] **Step 6: Run the full test suite as a regression check**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add library/quick_add.py tests/test_quick_add.py tests/test_physical_importer.py
git commit -m "Add quick_add.add_manga (ISBN and title paths)"
```

---

### Task 5: `/api/add-comic` and `/api/add-manga` routes

**Files:**
- Modify: `library/viewer_server.py`, `cli.py`
- Test: `tests/test_viewer_server.py`

**Interfaces:**
- Consumes: `quick_add.add_comic`, `quick_add.add_manga`, `quick_add.QuickAddError` (Tasks 2–4); `library.config.Config` (existing).
- Produces: `POST /api/add-comic`, `POST /api/add-manga` on `ViewerRequestHandler`; `ViewerRequestHandler.__init__` now requires a `config: Config` keyword argument.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_viewer_server.py`:

```python
def test_add_comic_endpoint_creates_new_record(server, monkeypatch):
    monkeypatch.setattr(
        "library.metadata_sources.comic_geeks.fetch_issue",
        lambda url: {"series": "Absolute Batman", "issue_number": "17", "publisher": "DC Comics"},
    )
    httpd, comics_path, _ = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/add-comic", {
        "input": "https://leagueofcomicgeeks.com/comic/1/absolute-batman-17",
        "formats": ["print"],
    })

    assert status == 200
    assert data["ok"] is True
    assert data["merged"] is False
    assert data["record"]["title"] == "Absolute Batman #17"
    records = load_library(comics_path)
    assert any(r.title == "Absolute Batman #17" for r in records.values())


def test_add_comic_endpoint_rejects_unrecognized_input(server):
    httpd, _, _ = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/add-comic", {"input": "not an identifier", "formats": ["print"]})

    assert status == 422
    assert "error" in data


def test_add_comic_endpoint_rejects_invalid_formats(server):
    httpd, _, _ = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/add-comic", {"input": "76194138584601011", "formats": ["ebook"]})

    assert status == 400
    assert "error" in data


def test_add_manga_endpoint_creates_new_record_in_manga_file(server, monkeypatch):
    monkeypatch.setattr(
        "library.metadata_sources.google_books.GoogleBooksSource.search",
        lambda self, title, year=None: {"author": "Hajime Isayama"},
    )
    monkeypatch.setattr(
        "library.metadata_sources.google_books.GoogleBooksSource.cover_image_url",
        lambda self, title, year=None: None,
    )
    httpd, comics_path, manga_path = server
    port = httpd.server_address[1]

    status, data = _post(port, "/api/add-manga", {"input": "Some New Series, Vol. 1", "formats": ["digital"]})

    assert status == 200
    assert data["ok"] is True
    records = load_library(manga_path)
    assert any(r.title == "Some New Series, Vol. 1" for r in records.values())
    assert load_library(comics_path).keys() == {"upc-1"}  # comics file untouched
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_viewer_server.py -v -k add_comic or add_manga
```

Expected: FAIL — 404 on the new routes (not yet registered).

- [ ] **Step 3: Implement the routes**

In `library/viewer_server.py`, add the import:

```python
from library.quick_add import QuickAddError, add_comic, add_manga
```

Register the two new routes in `do_POST`'s `routes` dict:

```python
            "/api/add-comic": self._add_comic,
            "/api/add-manga": self._add_manga,
```

Add the handler methods (near the other handlers, e.g. after `_delete_record`):

```python
    def _validate_formats(self, body: dict) -> list[str] | None:
        formats = body.get("formats")
        if not isinstance(formats, list) or not formats:
            return None
        if any(f not in _VALID_FORMATS for f in formats):
            return None
        return list(dict.fromkeys(formats))

    def _add_comic(self, body: dict) -> tuple[int, dict]:
        formats = self._validate_formats(body)
        if formats is None:
            return 400, {"error": "formats must be a non-empty list of 'digital'/'print'"}

        config = self.config
        metron = MetronSource(config.metron.username, config.metron.password) if config.metron.is_configured else None
        google_books = GoogleBooksSource(config.google_books.api_key)
        open_library = OpenLibrarySource()

        records = load_library(self.comics_path)
        try:
            result = add_comic(
                records, body["input"], formats,
                metron=metron, google_books=google_books, open_library=open_library, covers_dir=self.covers_dir,
            )
        except QuickAddError as e:
            return 422, {"error": str(e)}

        save_library(self.comics_path, records)
        return 200, {"ok": True, "merged": result.merged, "record": result.record.to_dict()}

    def _add_manga(self, body: dict) -> tuple[int, dict]:
        formats = self._validate_formats(body)
        if formats is None:
            return 400, {"error": "formats must be a non-empty list of 'digital'/'print'"}

        config = self.config
        google_books = GoogleBooksSource(config.google_books.api_key)
        open_library = OpenLibrarySource()

        records = load_library(self.manga_path)
        try:
            result = add_manga(
                records, body["input"], formats,
                google_books=google_books, open_library=open_library, covers_dir=self.covers_dir,
            )
        except QuickAddError as e:
            return 422, {"error": str(e)}

        save_library(self.manga_path, records)
        return 200, {"ok": True, "merged": result.merged, "record": result.record.to_dict()}
```

Add the corresponding imports at the top of `library/viewer_server.py`:

```python
from library.config import Config
from library.metadata_sources.google_books import GoogleBooksSource
from library.metadata_sources.metron import MetronSource
from library.metadata_sources.open_library import OpenLibrarySource
```

`load_config(config_path)` requires the file to exist and contain at least one entry under `roots:` (it raises `ValueError` otherwise) — it's written for the CLI's real `config.yaml`, not something a test double should have to satisfy on every request. The `serve` command already loads `config.yaml` once at startup (see `cli.py`'s existing `serve` command), so `ViewerRequestHandler.__init__` takes the already-loaded `Config` object itself (not a path), stored as `self.config`, alongside the existing `comics_path`/`manga_path`/`covers_dir` — `load_config` is never called from inside the handler at all:

```python
    def __init__(
        self,
        *args,
        comics_path: Path,
        manga_path: Path,
        covers_dir: Path,
        config: Config,
        **kwargs,
    ) -> None:
        self.comics_path = comics_path
        self.manga_path = manga_path
        self.covers_dir = covers_dir
        self.config = config
        super().__init__(*args, **kwargs)
```

Also refactor `_update_formats` to reuse the new `_validate_formats` helper instead of its inline duplicate check, since they must now stay identical:

```python
    def _update_formats(self, body: dict) -> tuple[int, dict]:
        record, records, path = self._find_record(body["id"])
        if record is None:
            return 404, {"error": f"No record with id {body['id']!r}"}

        formats = self._validate_formats(body)
        if formats is None:
            return 400, {"error": "formats must be a non-empty list of 'digital'/'print'"}

        set_formats(record, formats)
        save_library(path, records)
        return 200, {"ok": True, "record": record.to_dict()}
```

- [ ] **Step 4: Update `cli.py`'s `serve` command and the `server` test fixture to pass a `Config`**

In `cli.py`'s `serve` command, `config = load_config(config_path)` is already computed at the top of the function (existing line). Add `config=config` to the existing `functools.partial(...)` call, alongside `comics_path`/`manga_path`/`covers_dir`:

```python
    handler = functools.partial(
        ViewerRequestHandler, directory=".", comics_path=comics_path, manga_path=manga_path,
        covers_dir=covers_dir, config=config,
    )
```

In `tests/test_viewer_server.py`, add the import `from library.config import Config, GoogleBooksConfig, MetronConfig` and update the `server` fixture's `functools.partial(...)` call to pass a `Config` built directly (no YAML file needed — `MetronConfig()`'s defaults make `is_configured` `False`, matching "Metron not configured" in every other test file):

```python
    handler = functools.partial(
        ViewerRequestHandler,
        directory=str(tmp_path),
        comics_path=comics_path,
        manga_path=manga_path,
        covers_dir=covers_dir,
        config=Config(roots=[], metron=MetronConfig(), google_books=GoogleBooksConfig(), data_dir=tmp_path),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_viewer_server.py -v
```

Expected: PASS (all tests, including the 4 new ones).

- [ ] **Step 6: Run the full test suite as a regression check**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add library/viewer_server.py cli.py tests/test_viewer_server.py
git commit -m "Add /api/add-comic and /api/add-manga routes"
```

---

### Task 6: `AddItemForm` frontend + wire into `/admin`

**Files:**
- Create: `web/src/components/admin/AddItemForm.tsx`
- Modify: `web/src/App.tsx`

**Interfaces:**
- Consumes: nothing from earlier `web/` tasks except `App.tsx`'s existing `AdminPlaceholder` slot.
- Produces: `AddItemForm()` — a self-contained component with its own state, replacing `AdminPlaceholder` in `App.tsx`.

- [ ] **Step 1: Implement `AddItemForm.tsx`**

```tsx
// web/src/components/admin/AddItemForm.tsx
import { useState } from 'react'

type ItemType = 'comic' | 'manga'

interface AddResponse {
  ok: boolean
  merged: boolean
  record: { title: string; cover_path: string | null }
}

export function AddItemForm() {
  const [type, setType] = useState<ItemType>('comic')
  const [input, setInput] = useState('')
  const [digital, setDigital] = useState(false)
  const [print, setPrint] = useState(false)
  const [result, setResult] = useState<AddResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const formats = [...(digital ? ['digital'] : []), ...(print ? ['print'] : [])]
  const canSubmit = input.trim().length > 0 && formats.length > 0 && !submitting

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    setResult(null)

    const endpoint = type === 'comic' ? '/api/add-comic' : '/api/add-manga'
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input, formats }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? `Request failed (status ${res.status})`)
      } else {
        setResult(data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  const placeholder = type === 'comic' ? 'UPC, ISBN, or League of Comic Geeks link' : 'Title or ISBN'

  return (
    <form onSubmit={handleSubmit}>
      <h1>Add to collection</h1>
      <label>
        <input type="radio" checked={type === 'comic'} onChange={() => setType('comic')} />
        Comic
      </label>
      <label>
        <input type="radio" checked={type === 'manga'} onChange={() => setType('manga')} />
        Manga
      </label>

      <input
        type="text"
        placeholder={placeholder}
        value={input}
        onChange={(e) => setInput(e.target.value)}
      />

      <label>
        <input type="checkbox" checked={digital} onChange={(e) => setDigital(e.target.checked)} />
        Digital
      </label>
      <label>
        <input type="checkbox" checked={print} onChange={(e) => setPrint(e.target.checked)} />
        Physical
      </label>

      <button type="submit" disabled={!canSubmit}>
        {submitting ? 'Adding…' : 'Add'}
      </button>

      {error && <div role="alert">{error}</div>}
      {result && (
        <div>
          {result.merged ? 'Merged into existing record: ' : 'Added: '}
          {result.record.title}
          {result.record.cover_path && <img src={`/data/covers/${result.record.cover_path}`} alt={result.record.title} />}
        </div>
      )}
    </form>
  )
}
```

- [ ] **Step 2: Wire it into `App.tsx`**

In `web/src/App.tsx`, replace the `AdminPlaceholder` function and its usage:

```tsx
import { AddItemForm } from './components/admin/AddItemForm'
```

```tsx
export default function App() {
  const isAdmin = window.location.pathname === '/admin'
  return isAdmin ? <AddItemForm /> : <BrowsingView />
}
```

Delete the now-unused `AdminPlaceholder` function.

- [ ] **Step 3: Verify the build compiles**

```bash
cd web && npm run build
```

- [ ] **Step 4: Manual verification in headless Chrome via Playwright**

With `comic-library serve --port 8000` and `npm run dev` both running (per the shelf-skeleton plan's Task 10), navigate to `http://localhost:5173/admin` and, using a throwaway Playwright script:
- Submit a comic via a real UPC or Comic Geeks link (or ISBN) and confirm the success message + cover thumbnail render, then reload `http://localhost:5173/` and confirm the new item appears on the shelf.
- Submit a manga by title (one with no ISBN) and confirm it's added even if Google Books finds nothing.
- Submit garbage input (e.g. `"asdf"` for a comic) and confirm the inline error message renders and the form stays populated.

Delete the script when done.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/admin/AddItemForm.tsx web/src/App.tsx
git commit -m "Add AddItemForm and wire it into the /admin route"
```

## Self-Review Notes

- **Spec coverage:** Comic Geeks link / UPC / ISBN routing for comics (Tasks 2–3), ISBN/title routing for manga (Task 4), merge-vs-new-record behavior for both (Tasks 2–4), the two new routes with the spec's exact request/response shape (Task 5), the admin form with type toggle + single input + format checkboxes + result/error display (Task 6) — all covered. `formats` validation reuses `_update_formats`'s exact rule via the new shared `_validate_formats` helper (Task 5), per the spec's explicit requirement that they match.
- **Type/name consistency checked:** `AddResult`/`QuickAddError` (Task 2) used identically in Tasks 3–5. `add_comic`/`add_manga` signatures (Tasks 2–4) match their call sites in `viewer_server.py` (Task 5). `is_isbn_shaped`/`truncate_isbn`/`enrich_comic_by_upc`/`enrich_isbn` (Task 1's renames) are the exact names Task 3/4 import.
- **Gap fixed during review (config wiring):** the spec didn't say how `ViewerRequestHandler` gets a `MetronSource`/`GoogleBooksSource` (which need `config.yaml`). An initial draft called `load_config()` per-request with no path — wrong on two counts: `load_config` takes a required path argument, and it raises `ValueError` on a config with no `roots:` entries, which a test double would need to fake for no reason. Fixed by having `ViewerRequestHandler.__init__` take the already-loaded `Config` object itself (`config: Config`, stored as `self.config`) — `cli.py`'s `serve` command already calls `load_config` once at startup, so that object is threaded through `functools.partial(...)` instead of being reloaded, and the test fixture constructs a `Config` directly with no YAML file at all (Task 5, Steps 3–4).
- **Gap fixed during review (manga merge via bare ISBN):** `enrich_isbn` (promoted in Task 1) never fills `series`/`issue_number` — only author/publisher/year/description — matching the batch importer's own behavior, where a row's series/issue come from the *typed* sheet title, not from the ISBN lookup. A bare-ISBN quick-add input has no typed title at all, so merging into an existing digital record is genuinely impossible on that path, not just untested. Task 4's tests were corrected to assert exactly that (`test_add_manga_from_bare_isbn_never_merges_since_no_title_to_match_on`), with the real merge behavior verified on the title-input path instead (`test_add_manga_from_title_merges_into_existing_digital_record`), where `strip_manga_volume_suffix`/`extract_manga_issue` can actually derive a series + issue number to match on.
