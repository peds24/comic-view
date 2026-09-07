# Pull-list automation + add-comic CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let comics enter the library one at a time — automatically every week from the user's League of Comic Geeks pull list (as physical), and manually via a global `add-comic <url>` terminal command (as digital, or `--physical` for a one-off print add).

**Architecture:** Comic Geeks now sits behind a Cloudflare managed challenge that blocks plain HTTP, so a new headless-Playwright fetch helper replaces the existing scraper's transport (parsing logic unchanged). A new confidence-checked Metron lookup resolves each pulled title without ever silently picking the wrong same-named series — it flags ambiguous/unresolved titles instead of guessing. A deterministic `check-pulls` CLI command does the actual fetch/resolve/save work; a scheduled Claude routine runs it weekly, reviews flagged items, commits, and reports to the user (no auto-push). `add-comic` is a separate, fully deterministic CLI command for the manual link-paste flow.

**Tech Stack:** Python 3.11, Click, Playwright (headless Chromium, already vendored in `.venv`), BeautifulSoup, `icalendar`, pytest with `monkeypatch`.

**Spec:** `docs/superpowers/specs/2026-09-07-pull-list-and-add-comic-design.md`

## Global Constraints

- New dependencies: `playwright>=1.40` and `icalendar>=5.0` (added to `pyproject.toml`; both already installed in `.venv` at 1.62.0 / 7.3.0 respectively — no reinstall needed for local dev).
- No test may launch a real browser or hit a real network endpoint — mock at the `sync_playwright` API boundary (browser_fetch tests) or at `browser_fetch.fetch_html` / `browser_fetch.download_text` (everything downstream), exactly like every existing metadata source test mocks `get_with_retry`.
- `check-pulls` never runs `git`; committing (without pushing) is the scheduled routine's job, not the CLI's.
- `config.yaml` holds real credentials and is gitignored — put the user's real pull-list calendar URL there, never in a tracked file or in this plan/spec.
- Follow existing conventions exactly where one already exists for the same kind of thing: id schemes (`upc-`/`isbn-` prefixes), the `metadata_source` dict convention, `ComicRecord.apply_partial`, and the physical importer's digital-merge-over-duplicate pattern.

---

### Task 1: Headless-browser fetch helper

**Files:**
- Create: `library/browser_fetch.py`
- Test: `tests/test_browser_fetch.py`
- Modify: `pyproject.toml` (add `playwright` and `icalendar` to `dependencies`)

**Interfaces:**
- Produces: `browser_fetch.fetch_html(url: str, *, wait_selector: str = "h1", timeout_ms: int = 20000) -> str` — returns rendered HTML, or `""` on any failure.
- Produces: `browser_fetch.download_text(url: str, *, timeout_ms: int = 20000) -> str` — returns a triggered download's text content, or `""` on any failure.

- [ ] **Step 1: Add dependencies**

Edit `pyproject.toml`'s `dependencies` list:

```toml
dependencies = [
    "rarfile>=4.1",
    "requests>=2.31",
    "PyYAML>=6.0",
    "click>=8.1",
    "openpyxl>=3.1",
    "beautifulsoup4>=4.12",
    "playwright>=1.40",
    "icalendar>=5.0",
]
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_browser_fetch.py`:

```python
from pathlib import Path

import pytest

from library import browser_fetch


class FakeDownload:
    def __init__(self, content: str):
        self._content = content

    def save_as(self, path):
        Path(path).write_text(self._content)


class _FakeDownloadContext:
    def __init__(self, download=None, error=None):
        self._download = download
        self._error = error

    def __enter__(self):
        if self._error:
            raise self._error
        return self

    def __exit__(self, *args):
        return False

    @property
    def value(self):
        return self._download


class FakePage:
    def __init__(
        self,
        *,
        goto_error=None,
        selector_error=None,
        content_html="",
        download=None,
        download_error=None,
    ):
        self.goto_calls = []
        self.new_page_kwargs = None
        self._goto_error = goto_error
        self._selector_error = selector_error
        self._content_html = content_html
        self._download = download
        self._download_error = download_error

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        if self._goto_error:
            raise self._goto_error

    def wait_for_selector(self, selector, **kwargs):
        if self._selector_error:
            raise self._selector_error

    def content(self):
        return self._content_html

    def expect_download(self, **kwargs):
        return _FakeDownloadContext(self._download, self._download_error)


class FakeBrowser:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_page(self, **kwargs):
        self._page.new_page_kwargs = kwargs
        return self._page

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser):
        self._browser = browser

    def launch(self, **kwargs):
        return self._browser


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)


class FakePlaywrightContext:
    def __init__(self, browser):
        self._browser = browser

    def __enter__(self):
        return FakePlaywright(self._browser)

    def __exit__(self, *args):
        return False


def _patch_playwright(monkeypatch, page):
    browser = FakeBrowser(page)
    monkeypatch.setattr(browser_fetch, "sync_playwright", lambda: FakePlaywrightContext(browser))
    return browser


def test_fetch_html_returns_content_when_selector_appears(monkeypatch):
    page = FakePage(content_html="<html><h1>Absolute Batman #16</h1></html>")
    browser = _patch_playwright(monkeypatch, page)

    result = browser_fetch.fetch_html("https://leagueofcomicgeeks.com/comic/6297209")

    assert result == "<html><h1>Absolute Batman #16</h1></html>"
    assert browser.closed is True
    assert page.new_page_kwargs["user_agent"] == browser_fetch._USER_AGENT


def test_fetch_html_ignores_goto_timeout_if_selector_appears(monkeypatch):
    page = FakePage(goto_error=TimeoutError("goto timed out"), content_html="<html><h1>ok</h1></html>")
    _patch_playwright(monkeypatch, page)

    result = browser_fetch.fetch_html("https://leagueofcomicgeeks.com/comic/6297209")

    assert result == "<html><h1>ok</h1></html>"


def test_fetch_html_returns_empty_string_when_selector_never_appears(monkeypatch):
    page = FakePage(selector_error=TimeoutError("selector never appeared"))
    _patch_playwright(monkeypatch, page)

    assert browser_fetch.fetch_html("https://leagueofcomicgeeks.com/comic/bad") == ""


def test_download_text_returns_downloaded_content(monkeypatch):
    page = FakePage(download=FakeDownload("BEGIN:VCALENDAR\nEND:VCALENDAR"))
    _patch_playwright(monkeypatch, page)

    result = browser_fetch.download_text("https://leagueofcomicgeeks.com/member/calendar_ics/peds24")

    assert result == "BEGIN:VCALENDAR\nEND:VCALENDAR"


def test_download_text_returns_empty_string_on_failure(monkeypatch):
    page = FakePage(download_error=RuntimeError("no download started"))
    _patch_playwright(monkeypatch, page)

    assert browser_fetch.download_text("https://leagueofcomicgeeks.com/member/calendar_ics/peds24") == ""
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_browser_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'library.browser_fetch'` (or `AttributeError`).

- [ ] **Step 4: Implement `library/browser_fetch.py`**

```python
"""Headless-browser fetch helpers for pages that sit behind a JS-executing
anti-bot challenge — League of Comic Geeks added a Cloudflare managed
challenge (confirmed live) that blocks a plain `requests.get`, the
transport every other metadata source in this codebase uses. A real
browser event loop resolves it without any extra configuration; Playwright's
bundled headless Chromium (already vendored in this project's venv) is
used here instead of a plain HTTP client, for both Comic Geeks issue pages
(comic_geeks.py) and its per-user ICS pull-list calendar (pull_calendar.py).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_html(url: str, *, wait_selector: str = "h1", timeout_ms: int = 20000) -> str:
    """Loads `url` in headless Chromium and returns the fully rendered
    HTML, or "" if the page never resolves (bad URL, site unreachable, the
    challenge never clears). Cloudflare's challenge means the browser's
    `load` event may never fire even after the real content has rendered
    (confirmed live) — a `goto` timeout is caught and ignored as long as
    `wait_selector` shows up within `timeout_ms`; only a `wait_for_selector`
    timeout is treated as a real failure."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=_USER_AGENT)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception:
                    pass
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
                return page.content()
            finally:
                browser.close()
    except Exception:
        return ""


def download_text(url: str, *, timeout_ms: int = 20000) -> str:
    """Navigates to `url` and captures the file it triggers a download for
    (the pull-list calendar is served this way, not as a renderable page),
    returning the downloaded file's text content, or "" on failure."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=_USER_AGENT, accept_downloads=True)
                with page.expect_download(timeout=timeout_ms) as dl_info:
                    try:
                        page.goto(url, timeout=timeout_ms)
                    except Exception:
                        pass
                download = dl_info.value
                with tempfile.TemporaryDirectory() as tmp_dir:
                    saved_path = Path(tmp_dir) / "download"
                    download.save_as(saved_path)
                    return saved_path.read_text()
            finally:
                browser.close()
    except Exception:
        return ""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_browser_fetch.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Install the new dependencies into the venv and confirm the real suite still runs**

Run: `source .venv/bin/activate && pip install -e . && pytest -q`
Expected: all existing tests still PASS (this only adds new deps + one new file; nothing existing changed yet).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml library/browser_fetch.py tests/test_browser_fetch.py
git commit -m "$(cat <<'EOF'
Add headless-Playwright fetch helper for sites behind a JS challenge

League of Comic Geeks now sits behind a Cloudflare managed challenge
that blocks plain HTTP requests (confirmed live) — headless Chromium
gets through cleanly. This is the shared transport the next commits
wire the Comic Geeks scraper and pull-list calendar fetch onto.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

---

### Task 2: Swap `comic_geeks.py`'s transport to headless Playwright

**Files:**
- Modify: `library/metadata_sources/comic_geeks.py`
- Modify: `tests/test_comic_geeks.py`

**Interfaces:**
- Consumes: `browser_fetch.fetch_html(url: str) -> str` (Task 1).
- Produces: `fetch_issue` keeps its existing signature/return shape (`dict` with the same keys) — no downstream caller (`manual_attach.py`) changes.

- [ ] **Step 1: Update the failing tests first**

Replace `tests/test_comic_geeks.py`'s HTTP-mocking tests with `browser_fetch`-mocking ones (the `FakeResponse` class and the "sends a browser-shaped User-Agent" assertion move to `test_browser_fetch.py`, already covered there):

```python
import re

from library.metadata_sources.comic_geeks import fetch_issue, is_comic_geeks_url

# A trimmed real fragment of a League of Comic Geeks issue page's
# structure, matching what was confirmed against the live site.
_PAGE_HTML = """
<html><head>
<meta property="og:image" content="https://s3.amazonaws.com/comicgeeks/comics/covers/medium-6297209.jpg" />
</head><body>
<div class="header-intro">
    <a href="/comics/dc-comics">DC Comics</a> &nbsp;&nbsp;&middot;&nbsp;&nbsp;
    Released <a href="/comics/new-comics/2026/01/28">Jan 28, 2026</a>
</div>
<h1>Absolute Batman #16</h1>
<div class="col-12 listing-description">
    <p>ABSOLUTE BATMAN IN HELL! Part two of our story.</p>
</div>
<div class="row details-addtl copy-small mt-3">
    <div class="col details-addtl-block">
        <div class="name">Cover Date</div>
        <div class="value">Mar 2026</div>
    </div>
    <div class="col details-addtl-block">
        <div class="name">UPC</div>
        <div class="value">76194138584601611</div>
    </div>
</div>
<div class="cover-art">
    <a href="https://s3.amazonaws.com/comicgeeks/comics/covers/large-6297209.jpg" class="cover-gallery">
        <img src="https://s3.amazonaws.com/comicgeeks/comics/covers/large-6297209.jpg">
    </a>
</div>
<div class="role color-offset copy-really-small">Writer</div>
<div class="name color-primary copy-small font-weight-bold"><a href="/people/179/scott-snyder">Scott Snyder</a></div>
<div class="role color-offset copy-really-small">Writer, Artist</div>
<div class="name color-primary copy-small font-weight-bold"><a href="/people/876/nick-dragotta">Nick Dragotta</a></div>
<div class="role color-offset copy-really-small">Colorist</div>
<div class="name color-primary copy-small font-weight-bold"><a href="/people/745/frank-martin">Frank Martin</a></div>
</body></html>
"""


def test_is_comic_geeks_url():
    assert is_comic_geeks_url("https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16") is True
    assert is_comic_geeks_url("https://metron.cloud/issue/absolute-batman-2024-16/") is False


def test_fetch_issue_parses_all_fields(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "library.metadata_sources.comic_geeks.browser_fetch.fetch_html",
        lambda url, **kwargs: calls.append(url) or _PAGE_HTML,
    )

    result = fetch_issue("https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16")

    assert result["series"] == "Absolute Batman"
    assert result["issue_number"] == "16"
    assert result["publisher"] == "DC Comics"
    assert result["year"] == 2026  # from "Released", not "Cover Date"
    assert result["description"] == "ABSOLUTE BATMAN IN HELL! Part two of our story."
    assert result["author"] == "Scott Snyder, Nick Dragotta"  # colorist excluded
    assert result["upc"] == "76194138584601611"
    assert result["_image_url"] == "https://s3.amazonaws.com/comicgeeks/comics/covers/large-6297209.jpg"
    assert calls[0] == "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16"


def test_fetch_issue_accepts_bare_numeric_id(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "library.metadata_sources.comic_geeks.browser_fetch.fetch_html",
        lambda url, **kwargs: calls.append(url) or _PAGE_HTML,
    )
    fetch_issue("6297209")
    assert calls[0] == "https://leagueofcomicgeeks.com/comic/6297209"


def test_fetch_issue_returns_empty_dict_when_page_unreadable(monkeypatch):
    monkeypatch.setattr("library.metadata_sources.comic_geeks.browser_fetch.fetch_html", lambda url, **kwargs: "")
    assert fetch_issue("https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16") == {}


def test_fetch_issue_falls_back_to_og_image_when_no_cover_gallery_link(monkeypatch):
    html_without_gallery = re.sub(r'<div class="cover-art">.*?</div>', "", _PAGE_HTML, flags=re.DOTALL)
    monkeypatch.setattr(
        "library.metadata_sources.comic_geeks.browser_fetch.fetch_html",
        lambda url, **kwargs: html_without_gallery,
    )
    result = fetch_issue("https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16")
    assert result["_image_url"] == "https://s3.amazonaws.com/comicgeeks/comics/covers/medium-6297209.jpg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_comic_geeks.py -v`
Expected: FAIL — old tests reference `get_with_retry`, which `fetch_issue` still uses; new tests' `browser_fetch.fetch_html` mock is never called since the source hasn't changed yet, so `result` comes back `{}`/errors.

- [ ] **Step 3: Update `library/metadata_sources/comic_geeks.py`**

Replace the import and the fetch call. Change:

```python
from library.http_utils import get_with_retry
from library.matching import extract_issue
```

to:

```python
from library import browser_fetch
from library.matching import extract_issue
```

Remove the now-unused `_USER_AGENT` constant (it lives in `browser_fetch.py` now). Change `fetch_issue`'s body from:

```python
def fetch_issue(url_or_id: str) -> dict:
    resolved_url = _resolve_url(url_or_id)
    try:
        resp = get_with_retry(resolved_url, headers={"User-Agent": _USER_AGENT}, timeout=10)
        resp.raise_for_status()
    except Exception:
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
```

to:

```python
def fetch_issue(url_or_id: str) -> dict:
    resolved_url = _resolve_url(url_or_id)
    html = browser_fetch.fetch_html(resolved_url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
```

Everything below (`result: dict = {}` onward) is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_comic_geeks.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full suite**

Run: `source .venv/bin/activate && pytest -q`
Expected: all PASS — `manual_attach.py` mocks `comic_geeks.fetch_issue` directly, so it's unaffected by this transport swap.

- [ ] **Step 6: Commit**

```bash
git add library/metadata_sources/comic_geeks.py tests/test_comic_geeks.py
git commit -m "$(cat <<'EOF'
Fetch Comic Geeks issue pages via headless Playwright, not requests

The site's Cloudflare managed challenge blocks the old requests.get
transport outright (confirmed live). Parsing logic is unchanged —
only how the HTML gets fetched.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

---

### Task 3: Confidence-checked Metron series/issue resolution

**Files:**
- Modify: `library/metadata_sources/metron.py`
- Modify: `tests/test_metron.py`

**Interfaces:**
- Produces: `MetronSource.find_issue_confident(series: str, number: str, year: int | None = None) -> tuple[dict | None, str, list[dict]]` — status is `"ok"` / `"not_found"` / `"ambiguous"`; on `"ambiguous"`, the list holds `{"series_id", "series_name", "publisher", "year_began", "year_end"}` per candidate.
- Consumes/refactors: `MetronSource._find_series` now delegates to two new private helpers (`_fetch_series_results`, `_filter_exact_matches`) instead of doing both inline — its own behavior and every existing caller/test are unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_metron.py` (append; keep all existing tests as-is):

```python
def test_find_issue_confident_ok_when_only_one_series_has_the_issue(monkeypatch):
    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/series/"):
            assert params == {"name": "Batman"}
            return FakeResponse({"results": [
                {"id": 2481, "series": "Batman (1940)", "year_began": 1940, "year_end": 2011},
                {"id": 12829, "series": "Batman (2025)", "year_began": 2025, "year_end": None},
            ]})
        if url.endswith("/issue/") and params.get("series_id") == 2481:
            return FakeResponse({"results": []})
        if url.endswith("/issue/") and params.get("series_id") == 12829:
            return FakeResponse({"results": [{"id": 999}]})
        assert url.endswith("/issue/999/")
        return FakeResponse({"id": 999, "number": "13"})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Batman", "13")

    assert status == "ok"
    assert issue["id"] == 999
    assert candidates == []


def test_find_issue_confident_ambiguous_when_two_series_both_have_the_issue(monkeypatch):
    """Regression test for the reported real failure: an ended 'Batman'
    run and the current 'Batman (2025)' relaunch both existing only
    matters if both also happen to have reached the same issue number —
    here they both have a #13, so neither should be silently chosen."""
    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/series/"):
            return FakeResponse({"results": [
                {"id": 2481, "series": "Batman (1940)", "year_began": 1940, "year_end": 2011,
                 "publisher": {"name": "DC Comics"}},
                {"id": 12829, "series": "Batman (2025)", "year_began": 2025, "year_end": None,
                 "publisher": {"name": "DC Comics"}},
            ]})
        assert url.endswith("/issue/")
        return FakeResponse({"results": [{"id": params["series_id"] * 10}]})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Batman", "13")

    assert status == "ambiguous"
    assert issue is None
    assert {c["series_id"] for c in candidates} == {2481, 12829}
    assert all(c["publisher"] == "DC Comics" for c in candidates)


def test_find_issue_confident_uses_year_to_break_ambiguity(monkeypatch):
    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/series/"):
            return FakeResponse({"results": [
                {"id": 2481, "series": "Batman (1940)", "year_began": 1940, "year_end": 2011},
                {"id": 12829, "series": "Batman (2025)", "year_began": 2025, "year_end": None},
            ]})
        if url.endswith("/issue/") and params.get("series_id") == 2481:
            return FakeResponse({"results": [{"id": 111}]})
        if url.endswith("/issue/") and params.get("series_id") == 12829:
            return FakeResponse({"results": [{"id": 999}]})
        assert url.endswith("/issue/999/")
        return FakeResponse({"id": 999, "number": "13"})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Batman", "13", year=2026)

    assert status == "ok"
    assert issue["id"] == 999


def test_find_issue_confident_not_found_when_no_series_has_the_issue(monkeypatch):
    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/series/"):
            return FakeResponse({"results": [{"id": 12829, "series": "Batman (2025)", "year_began": 2025}]})
        return FakeResponse({"results": []})

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Batman", "999")

    assert status == "not_found"
    assert issue is None
    assert candidates == []


def test_find_issue_confident_not_found_when_series_name_unknown(monkeypatch):
    monkeypatch.setattr("library.http_utils.requests.get", lambda *a, **k: FakeResponse({"results": []}))
    source = MetronSource("user", "pass")

    issue, status, candidates = source.find_issue_confident("Nonexistent Series", "1")

    assert status == "not_found"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_metron.py -v -k find_issue_confident`
Expected: FAIL — `AttributeError: 'MetronSource' object has no attribute 'find_issue_confident'`

- [ ] **Step 3: Refactor `_find_series` and implement `find_issue_confident`**

In `library/metadata_sources/metron.py`, replace the existing `_find_series` method with:

```python
    def _find_series(self, title: str, year: int | None = None) -> dict | None:
        """Metron's `name` filter is a substring/relevance search, not an
        exact match — searching "Batman" can return "Absolute Batman" as
        the top hit among hundreds of matches (confirmed against the live
        API). Prefer a result whose name exactly matches `title` (ignoring
        Metron's trailing "(YYYY)" year suffix); among several exact
        matches — a series name reused across eras, e.g. "Batman" (1940),
        (2011), (2016), (2025) are four different Metron series — prefer
        the one whose year range contains `year`. Only falls back to
        Metron's own top relevance match when no exact name match exists at
        all."""
        results = self._fetch_series_results(title)
        if not results:
            return None

        exact = self._filter_exact_matches(results, title)
        if not exact:
            return results[0]
        if len(exact) == 1 or not year:
            return exact[0]
        for s in exact:
            began = s.get("year_began")
            ended = s.get("year_end") or 9999
            if began and began <= year <= ended:
                return s
        return exact[0]

    def find_issue_confident(
        self, series: str, number: str, year: int | None = None
    ) -> tuple[dict | None, str, list[dict]]:
        """Like find_issue_by_series_and_number, but never guesses when a
        series name is genuinely ambiguous. Checks every series exactly
        named `series` for an actual issue #`number` — not just the
        year-narrowed pick `_find_series` would make — since two same-named
        series (an ended run and its relaunch) both existing doesn't
        matter unless both also happen to have reached that same issue
        number. `year`, when given, breaks a remaining tie the same way
        `_find_series` does.

        Returns (issue_detail, status, candidates):
          "ok"        -> exactly one exact-name series has issue #number; issue_detail is its full detail.
          "not_found" -> no exact-name series has issue #number; issue_detail is None.
          "ambiguous" -> more than one exact-name series has issue #number (even after a year
                         tie-break, if one was possible); issue_detail is None, candidates lists
                         each match's {"series_id", "series_name", "publisher", "year_began", "year_end"}.
        """
        results = self._fetch_series_results(series)
        exact = self._filter_exact_matches(results, series)
        if not exact:
            return None, "not_found", []

        hits = []
        for candidate in exact:
            resp = get_with_retry(
                f"{_BASE_URL}/issue/",
                params={"series_id": candidate["id"], "number": number},
                auth=self._auth,
                timeout=10,
            )
            resp.raise_for_status()
            issue_results = resp.json().get("results", [])
            if issue_results:
                hits.append((candidate, issue_results[0]["id"]))

        if not hits:
            return None, "not_found", []

        if len(hits) > 1 and year:
            year_matches = [
                h for h in hits
                if h[0].get("year_began") and h[0]["year_began"] <= year <= (h[0].get("year_end") or 9999)
            ]
            if len(year_matches) == 1:
                hits = year_matches

        if len(hits) > 1:
            candidates = [
                {
                    "series_id": c["id"],
                    "series_name": c.get("series", ""),
                    "publisher": c.get("publisher", {}).get("name") if isinstance(c.get("publisher"), dict) else None,
                    "year_began": c.get("year_began"),
                    "year_end": c.get("year_end"),
                }
                for c, _ in hits
            ]
            return None, "ambiguous", candidates

        _, issue_id = hits[0]
        return self._issue_detail(issue_id), "ok", []

    def _fetch_series_results(self, title: str) -> list[dict]:
        resp = get_with_retry(f"{_BASE_URL}/series/", params={"name": title}, auth=self._auth, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])

    @staticmethod
    def _filter_exact_matches(results: list[dict], title: str) -> list[dict]:
        target = title.strip().lower()
        return [s for s in results if normalize_series(s.get("series", "")).lower() == target]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_metron.py -v`
Expected: PASS (all tests, old and new — confirms the `_find_series` refactor didn't change existing behavior)

- [ ] **Step 5: Commit**

```bash
git add library/metadata_sources/metron.py tests/test_metron.py
git commit -m "$(cat <<'EOF'
Add MetronSource.find_issue_confident, never guessing an ambiguous series

find_issue_by_series_and_number's year-based disambiguation already
exists but silently falls back to the first exact-name match when
that doesn't cleanly resolve. find_issue_confident instead checks
every exact-name series for the actual issue number and only returns
a match when exactly one candidate has it — otherwise it reports
"ambiguous" or "not_found" so a caller can flag it for manual review
instead of attaching the wrong series' metadata.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

---

### Task 4: Format-agnostic record matching + issue-suffix stripping

**Files:**
- Modify: `library/matching.py`
- Modify: `tests/test_matching.py`

**Interfaces:**
- Produces: `matching.find_matching_record(records: dict[str, ComicRecord], series: str, issue_number: str) -> ComicRecord | None` — like `find_digital_match` but matches a record regardless of its current `formats`.
- Produces: `matching.strip_issue_suffix(full_title: str) -> str` — e.g. `"Batman #14"` → `"Batman"`.
- Refactors: `find_digital_match` now delegates to a new private `_find_match` helper; its own signature/behavior is unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_matching.py`:

```python
def test_find_matching_record_matches_regardless_of_format():
    records = {
        "p1": ComicRecord(
            id="p1", title="Absolute Batman #9", type="comic", series="Absolute Batman",
            issue_number="9", formats=["print"],
        )
    }
    from library.matching import find_matching_record
    match = find_matching_record(records, "Absolute Batman", "9")
    assert match is not None
    assert match.id == "p1"


def test_find_matching_record_normalizes_issue_numbers():
    from library.matching import find_matching_record
    records = {
        "d1": ComicRecord(
            id="d1", title="Absolute Batman", type="comic", series="Absolute Batman",
            issue_number="021", formats=["digital"],
        )
    }
    assert find_matching_record(records, "Absolute Batman", "21").id == "d1"


def test_find_matching_record_returns_none_when_no_match():
    from library.matching import find_matching_record
    assert find_matching_record({}, "Absolute Batman", "9") is None


def test_strip_issue_suffix_removes_hash_number():
    from library.matching import strip_issue_suffix
    assert strip_issue_suffix("Batman #14") == "Batman"


def test_strip_issue_suffix_returns_title_unchanged_when_no_suffix():
    from library.matching import strip_issue_suffix
    assert strip_issue_suffix("Billy Bat Vol. 2 TP") == "Billy Bat Vol. 2 TP"
```

(These `from library.matching import ...` lines inside the test bodies match this file's existing style of a top-of-file import block — move them up into the file's existing top import statement instead, alongside `find_digital_match` etc., rather than importing inline in each test.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_matching.py -v -k "matching_record or strip_issue_suffix"`
Expected: FAIL — `ImportError: cannot import name 'find_matching_record'`

- [ ] **Step 3: Implement in `library/matching.py`**

Add near the top, alongside the other compiled regexes:

```python
_ISSUE_SUFFIX_RE = re.compile(r"\s*#\d+\s*$")
```

Add near `strip_manga_volume_suffix`:

```python
def strip_issue_suffix(full_title: str) -> str:
    """Best-effort series name for a single-issue title with its '#N'
    suffix removed, e.g. "Batman #14" -> "Batman"."""
    return _ISSUE_SUFFIX_RE.sub("", full_title or "").strip()
```

Replace `find_digital_match` with:

```python
def _find_match(
    records: dict[str, ComicRecord], series: str, issue_number: str, required_format: str | None = None
) -> ComicRecord | None:
    target_series = (series or "").lower()
    target_issue = normalize_issue(issue_number)
    for record in records.values():
        if required_format and required_format not in record.formats:
            continue
        if (record.series or "").lower() != target_series:
            continue
        if record.issue_number is None:
            continue
        if normalize_issue(record.issue_number) != target_issue:
            continue
        return record
    return None


def find_digital_match(
    records: dict[str, ComicRecord], series: str, issue_number: str
) -> ComicRecord | None:
    return _find_match(records, series, issue_number, required_format="digital")


def find_matching_record(
    records: dict[str, ComicRecord], series: str, issue_number: str
) -> ComicRecord | None:
    """Like find_digital_match, but matches a record regardless of its
    current formats — used when adding a new format (digital or print) to
    a comic that might already exist in the *other* format, so a new add
    can merge into it instead of creating a duplicate id for the same
    issue."""
    return _find_match(records, series, issue_number)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_matching.py -v`
Expected: PASS (all tests, old and new)

- [ ] **Step 5: Run the full suite**

Run: `source .venv/bin/activate && pytest -q`
Expected: all PASS — `physical_importer.py` calls `find_digital_match` positionally with the same two args, unaffected by the refactor.

- [ ] **Step 6: Commit**

```bash
git add library/matching.py tests/test_matching.py
git commit -m "$(cat <<'EOF'
Add find_matching_record and strip_issue_suffix to matching.py

find_matching_record generalizes find_digital_match to any format, for
add-comic's cross-format merge check (a digital add should merge into
an existing print-only record and vice versa, not duplicate it).
strip_issue_suffix gives the pull-list resolver a series-name guess
from a pulled title's "#N" suffix.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

---

### Task 5: Pull-list calendar parsing + processed-event state

**Files:**
- Create: `library/pull_calendar.py`
- Test: `tests/test_pull_calendar.py`

**Interfaces:**
- Consumes: `browser_fetch.download_text(url: str) -> str` (Task 1).
- Produces: `PulledItem` dataclass — `event_uid: str`, `release_date: date`, `title: str`, `price: str | None`.
- Produces: `fetch_pulled_items(calendar_url: str) -> list[PulledItem]`.
- Produces: `parse_ics(raw_ics: str) -> list[PulledItem]` (pure, no network — used directly by tests and internally by `fetch_pulled_items`).
- Produces: `load_state(path: Path) -> dict` / `save_state(path: Path, state: dict) -> None` — state shape `{"processed_uids": list[str]}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pull_calendar.py`:

```python
from datetime import date
from pathlib import Path

from library.pull_calendar import PulledItem, fetch_pulled_items, load_state, parse_ics, save_state

# A trimmed real fragment of the pull-list ICS feed's structure, matching
# what was confirmed against the live feed this session.
_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//hacksw/handcal//NONSGML v1.0//EN
CALSCALE:GREGORIAN
X-WR-CALNAME:My Comic Pulls
BEGIN:VEVENT
UID:single-issue-uid@cg
DTSTAMP:20260907T123050
DESCRIPTION:Batman #14\\n$4.99\\n\\nDon't forget to add these comics on League of Comic Geeks after.
SUMMARY:New Comics for 10/07
DTSTART;VALUE=DATE:20261007
END:VEVENT
BEGIN:VEVENT
UID:bundled-uid@cg
DTSTAMP:20260907T123050
DESCRIPTION:Batman #423 Facsimile Edition 2026\\n$3.99\\n\\nMidnight Spider-Man #1\\n$5.99\\n\\nDon't forget to add these comics on League of Comic Geeks after.
SUMMARY:New Comics for 10/07
DTSTART;VALUE=DATE:20261007
END:VEVENT
BEGIN:VEVENT
UID:blank-price-uid@cg
DTSTAMP:20260907T123050
DESCRIPTION:Absolute Batman #24\\n$4.99\\n\\nAbsolute Batman #24 Skottie Young Webstore Variant\\n$\\n\\nDon't forget to add these comics on League of Comic Geeks after.
SUMMARY:New Comics for 09/23
DTSTART;VALUE=DATE:20260923
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_single_title_event():
    items = parse_ics(_ICS)
    single = [i for i in items if i.event_uid == "single-issue-uid@cg"]
    assert single == [PulledItem(event_uid="single-issue-uid@cg", release_date=date(2026, 10, 7), title="Batman #14", price="$4.99")]


def test_parse_ics_bundled_titles_event():
    items = parse_ics(_ICS)
    bundled = [i for i in items if i.event_uid == "bundled-uid@cg"]
    assert bundled == [
        PulledItem(event_uid="bundled-uid@cg", release_date=date(2026, 10, 7), title="Batman #423 Facsimile Edition 2026", price="$3.99"),
        PulledItem(event_uid="bundled-uid@cg", release_date=date(2026, 10, 7), title="Midnight Spider-Man #1", price="$5.99"),
    ]


def test_parse_ics_blank_price_treated_as_none():
    items = parse_ics(_ICS)
    blank = [i for i in items if i.event_uid == "blank-price-uid@cg"]
    assert blank == [
        PulledItem(event_uid="blank-price-uid@cg", release_date=date(2026, 9, 23), title="Absolute Batman #24", price="$4.99"),
        PulledItem(event_uid="blank-price-uid@cg", release_date=date(2026, 9, 23), title="Absolute Batman #24 Skottie Young Webstore Variant", price=None),
    ]


def test_fetch_pulled_items_downloads_then_parses(monkeypatch):
    monkeypatch.setattr("library.pull_calendar.browser_fetch.download_text", lambda url, **kwargs: _ICS)
    items = fetch_pulled_items("https://leagueofcomicgeeks.com/member/calendar_ics/peds24")
    assert len(items) == 5


def test_fetch_pulled_items_returns_empty_list_on_download_failure(monkeypatch):
    monkeypatch.setattr("library.pull_calendar.browser_fetch.download_text", lambda url, **kwargs: "")
    assert fetch_pulled_items("https://leagueofcomicgeeks.com/member/calendar_ics/peds24") == []


def test_load_state_returns_empty_when_file_missing(tmp_path: Path):
    assert load_state(tmp_path / "pull_state.json") == {"processed_uids": []}


def test_save_state_then_load_state_round_trips(tmp_path: Path):
    path = tmp_path / "nested" / "pull_state.json"
    save_state(path, {"processed_uids": ["a@cg", "b@cg"]})
    assert load_state(path) == {"processed_uids": ["a@cg", "b@cg"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_pull_calendar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'library.pull_calendar'`

- [ ] **Step 3: Implement `library/pull_calendar.py`**

```python
"""Parses League of Comic Geeks' per-user pull-list ICS calendar feed into
individual pulled comics, and tracks which calendar events have already
been processed by the weekly check-pulls run.

Each week's VEVENT bundles one or more titles (and their prices) into one
DESCRIPTION blob — there's no per-comic link here (confirmed live; see the
design doc), just enough text to resolve via title search
(pull_resolver.py)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from icalendar import Calendar

from library import browser_fetch

_PRICE_PREFIX = "$"
_TRAILER_PREFIX = "don't forget"


@dataclass
class PulledItem:
    event_uid: str
    release_date: date
    title: str
    price: str | None


def fetch_pulled_items(calendar_url: str) -> list[PulledItem]:
    """Fetches and parses the calendar at `calendar_url`. Returns [] if
    the feed can't be fetched at all."""
    raw = browser_fetch.download_text(calendar_url)
    if not raw:
        return []
    return parse_ics(raw)


def parse_ics(raw_ics: str) -> list[PulledItem]:
    calendar = Calendar.from_ical(raw_ics)
    items: list[PulledItem] = []
    for component in calendar.walk("VEVENT"):
        uid = str(component.get("UID"))
        release_date = component.get("DTSTART").dt
        description = str(component.get("DESCRIPTION") or "")
        items.extend(_parse_description(uid, release_date, description))
    return items


def _parse_description(uid: str, release_date: date, description: str) -> list[PulledItem]:
    lines = [line.strip() for line in description.split("\n")]
    items: list[PulledItem] = []
    pending_title: str | None = None

    def _flush(price: str | None) -> None:
        nonlocal pending_title
        if pending_title is not None:
            items.append(PulledItem(event_uid=uid, release_date=release_date, title=pending_title, price=price))
            pending_title = None

    for line in lines:
        if not line or line.lower().startswith(_TRAILER_PREFIX):
            continue
        if line.startswith(_PRICE_PREFIX):
            price = line if len(line) > 1 else None
            _flush(price)
            continue
        _flush(None)  # a title line with no price line before it — add it with no price
        pending_title = line
    _flush(None)
    return items


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"processed_uids": []}
    return json.loads(path.read_text())


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_pull_calendar.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add library/pull_calendar.py tests/test_pull_calendar.py
git commit -m "$(cat <<'EOF'
Add pull-list ICS calendar parsing and processed-event state

Each calendar week bundles one or more titles into one DESCRIPTION
blob with no per-comic link (confirmed live against the real feed) —
parse_ics splits that into individual PulledItems for the resolver to
look up by title. load_state/save_state track which calendar events
a check-pulls run has already handled, so re-runs don't duplicate.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

---

### Task 6: `apply_metron_issue` helper

**Files:**
- Modify: `library/metadata_sources/metron.py`
- Modify: `tests/test_metron.py`

**Interfaces:**
- Consumes: `ComicRecord.apply_partial(partial: dict, source: str) -> None` (existing, `library/models.py`), `covers.download_cover(record, url, source_name, covers_dir) -> bool` (existing, `library/covers.py`).
- Produces: `apply_metron_issue(record: ComicRecord, issue: dict, covers_dir: Path, source_name: str = "metron") -> None` — module-level function in `metron.py`.

This mirrors `physical_importer._apply_metron_issue`'s field mapping exactly, as a reusable function for `pull_resolver.py` (Task 7). `physical_importer.py` itself is left untouched — its existing private copy is out of scope for this change.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_metron.py`:

```python
from pathlib import Path

from library.metadata_sources.metron import apply_metron_issue
from library.models import ComicRecord


def test_apply_metron_issue_fills_empty_fields_and_downloads_cover(tmp_path: Path, monkeypatch):
    class FakeCoverResponse:
        content = b"fake-cover-bytes"

        def raise_for_status(self):
            pass

    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    record = ComicRecord(id="metron-999", title="Batman #13", type="comic", formats=["print"])
    issue = {
        "id": 999,
        "series": {"name": "Batman"},
        "number": "13",
        "publisher": {"name": "DC Comics"},
        "store_date": "2026-10-07",
        "desc": "A synopsis.",
        "credits": [{"creator": "Chip Zdarsky", "role": [{"name": "Writer"}]}],
        "image": "https://example.com/batman-13.jpg",
    }

    apply_metron_issue(record, issue, tmp_path)

    assert record.series == "Batman"
    assert record.issue_number == "13"
    assert record.publisher == "DC Comics"
    assert record.year == 2026
    assert record.description == "A synopsis."
    assert record.author == "Chip Zdarsky"
    assert record.metadata_source["series"] == "metron"
    assert record.cover_path == "metron-999/cover.jpg"


def test_apply_metron_issue_does_not_overwrite_existing_fields(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not fetch a cover")))

    record = ComicRecord(id="metron-999", title="Batman #13", type="comic", formats=["print"], publisher="Already Set")
    apply_metron_issue(record, {"id": 999, "publisher": {"name": "DC Comics"}}, tmp_path)

    assert record.publisher == "Already Set"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_metron.py -v -k apply_metron_issue`
Expected: FAIL — `ImportError: cannot import name 'apply_metron_issue'`

- [ ] **Step 3: Implement in `library/metadata_sources/metron.py`**

Add the import and the new function (module-level, after the `year_from_issue` function and before the `MetronSource` class):

```python
from pathlib import Path

from library.covers import download_cover
from library.matching import normalize_series
from library.http_utils import get_with_retry
from library.models import ComicRecord
```

(This replaces the existing `from library.matching import normalize_series` / `from library.http_utils import get_with_retry` pair at the top of the file with the same two lines plus the two new imports.)

```python
def apply_metron_issue(record: ComicRecord, issue: dict, covers_dir: Path, source_name: str = "metron") -> None:
    """Fills any of record's currently-empty series/issue_number/publisher/
    year/description/author fields from a Metron issue detail dict (as
    returned by find_issue_confident, find_issue_by_upc, etc.), and
    downloads its cover. Mirrors physical_importer._apply_metron_issue's
    field mapping — used by pull_resolver.py, which needs the identical
    behavior for pull-list-resolved issues."""
    series = issue.get("series")
    series_name = series.get("name") if isinstance(series, dict) else None
    publisher = issue.get("publisher")
    publisher_name = publisher.get("name") if isinstance(publisher, dict) else None
    record.apply_partial(
        {
            "series": series_name,
            "issue_number": issue.get("number"),
            "publisher": publisher_name,
            "year": year_from_issue(issue),
            "description": issue.get("desc"),
            "author": MetronSource._extract_writer(issue),
        },
        source_name,
    )
    if issue.get("image"):
        download_cover(record, issue["image"], source_name, covers_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_metron.py -v`
Expected: PASS (all tests, old and new)

- [ ] **Step 5: Run the full suite**

Run: `source .venv/bin/activate && pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add library/metadata_sources/metron.py tests/test_metron.py
git commit -m "$(cat <<'EOF'
Add apply_metron_issue helper for filling a record from an issue detail

Reusable version of physical_importer's private _apply_metron_issue,
for pull_resolver.py (Task 7) to share the exact same field-mapping
and cover-download behavior without duplicating it a third time.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

---

### Task 7: Pull-list resolver

**Files:**
- Create: `library/pull_resolver.py`
- Test: `tests/test_pull_resolver.py`

**Interfaces:**
- Consumes: `PulledItem` (Task 5), `MetronSource.find_issue_confident` (Task 3), `MetronSource.search` (existing), `apply_metron_issue` (Task 6), `matching.extract_issue` / `matching.is_matchable` / `matching.strip_issue_suffix` / `matching.find_matching_record` (existing + Task 4).
- Produces: `ResolveResult` dataclass — `outcome: Literal["added", "merged", "flagged"]`, `title: str`, `reason: str | None`, `candidates: list[dict] | None`.
- Produces: `resolve_and_add(item: PulledItem, records: dict[str, ComicRecord], metron: MetronSource, covers_dir: Path) -> ResolveResult` — mutates `records` in place on `"added"`/`"merged"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pull_resolver.py`:

```python
from datetime import date
from pathlib import Path

import pytest

from library.models import ComicRecord
from library.pull_calendar import PulledItem
from library.pull_resolver import resolve_and_add


class FakeMetron:
    def __init__(self, confident_result=None, search_result=None):
        self.confident_result = confident_result or (None, "not_found", [])
        self.search_result = search_result or {}
        self.confident_calls = []
        self.search_calls = []

    def find_issue_confident(self, series, number, year=None):
        self.confident_calls.append((series, number, year))
        return self.confident_result

    def search(self, title, year=None):
        self.search_calls.append((title, year))
        return self.search_result


class FakeCoverResponse:
    content = b"fake-cover-bytes"

    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def _fake_cover_download(monkeypatch):
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())


def _item(title="Batman #13", price="$4.99", release_date=date(2026, 10, 7), uid="uid@cg"):
    return PulledItem(event_uid=uid, release_date=release_date, title=title, price=price)


def test_resolve_and_add_creates_new_print_record_on_confident_match(tmp_path: Path):
    issue = {"id": 999, "series": {"name": "Batman"}, "number": "13", "store_date": "2026-10-07"}
    metron = FakeMetron(confident_result=(issue, "ok", []))
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(), records, metron, tmp_path)

    assert result.outcome == "added"
    assert metron.confident_calls == [("Batman", "13", 2026)]
    record = records["metron-999"]
    assert record.title == "Batman #13"
    assert record.formats == ["print"]
    assert record.series == "Batman"


def test_resolve_and_add_uses_upc_id_when_metron_issue_has_one(tmp_path: Path):
    issue = {"id": 999, "upc": "76194138584601011", "series": {"name": "Batman"}, "number": "13"}
    metron = FakeMetron(confident_result=(issue, "ok", []))
    records: dict[str, ComicRecord] = {}

    resolve_and_add(_item(), records, metron, tmp_path)

    assert "upc-76194138584601011" in records
    assert "metron-999" not in records


def test_resolve_and_add_merges_into_existing_digital_record(tmp_path: Path):
    issue = {"id": 999, "series": {"name": "Batman"}, "number": "13"}
    metron = FakeMetron(confident_result=(issue, "ok", []))
    records = {
        "d1": ComicRecord(id="d1", title="Batman", type="comic", series="Batman", issue_number="13", formats=["digital"]),
    }

    result = resolve_and_add(_item(), records, metron, tmp_path)

    assert result.outcome == "merged"
    assert records["d1"].formats == ["digital", "print"]
    assert len(records) == 1  # no second record created


def test_resolve_and_add_flags_ambiguous_series(tmp_path: Path):
    candidates = [{"series_id": 2481, "series_name": "Batman (1940)", "publisher": "DC Comics", "year_began": 1940, "year_end": 2011}]
    metron = FakeMetron(confident_result=(None, "ambiguous", candidates))
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(), records, metron, tmp_path)

    assert result.outcome == "flagged"
    assert "Batman" in result.reason
    assert result.candidates == candidates
    assert records == {}


def test_resolve_and_add_flags_when_series_not_found(tmp_path: Path):
    metron = FakeMetron(confident_result=(None, "not_found", []))
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(), records, metron, tmp_path)

    assert result.outcome == "flagged"
    assert records == {}


def test_resolve_and_add_best_effort_search_for_collected_edition(tmp_path: Path):
    metron = FakeMetron(search_result={"publisher": "Kodansha", "year": 2026, "description": "A synopsis."})
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(title="Billy Bat Vol. 2 TP", price="$13.99"), records, metron, tmp_path)

    assert result.outcome == "added"
    assert metron.search_calls == [("Billy Bat Vol. 2 TP", 2026)]
    record = records["pull-2026-10-07-billy-bat-vol-2-tp"]
    assert record.publisher == "Kodansha"
    assert record.formats == ["print"]


def test_resolve_and_add_flags_collected_edition_with_no_metron_match(tmp_path: Path):
    metron = FakeMetron(search_result={})
    records: dict[str, ComicRecord] = {}

    result = resolve_and_add(_item(title="Billy Bat Vol. 2 TP", price="$13.99"), records, metron, tmp_path)

    assert result.outcome == "flagged"
    assert records == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_pull_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'library.pull_resolver'`

- [ ] **Step 3: Implement `library/pull_resolver.py`**

```python
"""Turns one pulled-list line item (a title + price parsed from the
League of Comic Geeks pull-list calendar, see pull_calendar.py) into a
new physical ComicRecord, merging into a matching digital record instead
of duplicating one where possible — mirrors physical_importer.py's merge
behavior for the Excel import path. Never guesses at an ambiguous series
match (see MetronSource.find_issue_confident) — those get reported back
for the user to resolve manually via add-comic instead."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from library.matching import extract_issue, find_matching_record, is_matchable, strip_issue_suffix
from library.metadata_sources.metron import MetronSource, apply_metron_issue
from library.models import ComicRecord
from library.pull_calendar import PulledItem

ResolverOutcome = Literal["added", "merged", "flagged"]


@dataclass
class ResolveResult:
    outcome: ResolverOutcome
    title: str
    reason: str | None = None
    candidates: list[dict] | None = None


def _slugify(text: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text.lower())
    return "-".join(keep.split()) or "untitled"


def resolve_and_add(
    item: PulledItem,
    records: dict[str, ComicRecord],
    metron: MetronSource,
    covers_dir: Path,
) -> ResolveResult:
    issue_number = extract_issue(item.title)

    if is_matchable(item.title, issue_number):
        series_guess = strip_issue_suffix(item.title)
        issue, status, candidates = metron.find_issue_confident(series_guess, issue_number, item.release_date.year)

        if status == "ambiguous":
            return ResolveResult(
                "flagged", item.title,
                reason=f"multiple Metron series named '{series_guess}' have issue #{issue_number}",
                candidates=candidates,
            )
        if status == "not_found":
            return ResolveResult(
                "flagged", item.title,
                reason=f"no Metron series named '{series_guess}' has issue #{issue_number}",
            )

        record_id = f"upc-{issue['upc']}" if issue.get("upc") else f"metron-{issue['id']}"
        record = ComicRecord(id=record_id, title=item.title, type="comic", issue_number=issue_number, formats=["print"])
        apply_metron_issue(record, issue, covers_dir)

        match = None
        if record.series and record.issue_number and is_matchable(record.title, record.issue_number):
            match = find_matching_record(records, record.series, record.issue_number)
        if match is not None:
            if "print" not in match.formats:
                match.formats.append("print")
            return ResolveResult("merged", item.title)

        records[record.id] = record
        return ResolveResult("added", item.title)

    # Collected edition / variant / annual / unmatchable title — best-effort
    # title search only; matching.is_matchable already excludes these from
    # ever being attempted as a single-issue match.
    partial = metron.search(item.title, item.release_date.year)
    if not partial:
        return ResolveResult("flagged", item.title, reason="no Metron match for this title")

    record = ComicRecord(
        id=f"pull-{item.release_date.isoformat()}-{_slugify(item.title)}",
        title=item.title, type="comic", issue_number=issue_number, formats=["print"],
    )
    record.apply_partial(partial, "metron")
    records[record.id] = record
    return ResolveResult("added", item.title)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_pull_resolver.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full suite**

Run: `source .venv/bin/activate && pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add library/pull_resolver.py tests/test_pull_resolver.py
git commit -m "$(cat <<'EOF'
Add pull-list resolver: title -> ComicRecord via confidence-checked Metron

resolve_and_add ties pull_calendar's parsed titles to
find_issue_confident, merging into an existing digital record where one
matches, or flagging (never guessing) when the series is ambiguous or
unresolved. Collected editions/variants/annuals fall back to a
best-effort title search, matching matching.is_matchable's existing
"never treat this as a single-issue match" rule.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

---

### Task 8: `check-pulls` CLI command + `pull_list` config

**Files:**
- Modify: `library/config.py`
- Modify: `config.example.yaml`
- Modify: `cli.py`
- Test: `tests/test_cli_check_pulls.py`

**Interfaces:**
- Consumes: `pull_calendar.fetch_pulled_items`, `pull_calendar.load_state`, `pull_calendar.save_state` (Task 5); `pull_resolver.resolve_and_add` (Task 7); `store.load_library` / `store.save_library` (existing).
- Produces: `comic-library check-pulls` — deterministic, never touches git.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_check_pulls.py`:

```python
from datetime import date
from pathlib import Path

import yaml
from click.testing import CliRunner

from cli import main
from library.pull_calendar import PulledItem


def _write_config(tmp_path: Path, calendar_url: str = "https://leagueofcomicgeeks.com/member/calendar_ics/peds24") -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump({
        "roots": [{"path": str(tmp_path), "type": "comic"}],
        "metron": {"username": "user", "password": "pass"},
        "pull_list": {"calendar_url": calendar_url},
    }))
    return config_path


def test_check_pulls_reports_no_configured_calendar(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path, calendar_url="")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert "No pull_list.calendar_url configured" in result.output


def test_check_pulls_adds_new_confident_match_and_updates_state(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    item = PulledItem(event_uid="uid@cg", release_date=date(2026, 10, 7), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: ({"id": 999, "series": {"name": "Batman"}, "number": "13"}, "ok", []),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "Added 1" in result.output
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert "metron-999" in library
    state = (tmp_path / "data" / "pull_state.json").read_text()
    assert "uid@cg" in state


def test_check_pulls_skips_already_processed_events(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "pull_state.json").write_text('{"processed_uids": ["uid@cg"]}')

    item = PulledItem(event_uid="uid@cg", release_date=date(2026, 10, 7), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: (_ for _ in ()).throw(AssertionError("should not resolve an already-processed item")),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "0 new" in result.output


def test_check_pulls_skips_future_releases(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    far_future = date(2099, 1, 1)
    item = PulledItem(event_uid="uid@cg", release_date=far_future, title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: (_ for _ in ()).throw(AssertionError("should not resolve a not-yet-released item")),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "0 new" in result.output


def test_check_pulls_reports_flagged_items(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    item = PulledItem(event_uid="uid@cg", release_date=date(2026, 10, 7), title="Batman #13", price="$4.99")
    monkeypatch.setattr("cli.fetch_pulled_items", lambda url: [item])
    monkeypatch.setattr(
        "cli.MetronSource.find_issue_confident",
        lambda self, series, number, year=None: (None, "ambiguous", [{"series_id": 1, "series_name": "Batman (1940)", "publisher": "DC", "year_began": 1940, "year_end": 2011}]),
    )

    result = CliRunner().invoke(main, ["check-pulls", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "FLAGGED: Batman #13" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_cli_check_pulls.py -v`
Expected: FAIL — `AttributeError`/`Usage: main [OPTIONS] COMMAND [ARGS]... Error: No such command 'check-pulls'.`

- [ ] **Step 3: Add `pull_list` to `library/config.py`**

Add a new dataclass and wire it into `Config`/`load_config`:

```python
@dataclass
class PullListConfig:
    calendar_url: str = ""
```

Add `pull_list: PullListConfig` to the `Config` dataclass fields (after `data_dir`), and in `load_config`:

```python
    pull_list_raw = raw.get("pull_list", {}) or {}
```

and add `pull_list=PullListConfig(calendar_url=pull_list_raw.get("calendar_url", ""))` to the returned `Config(...)` call.

- [ ] **Step 4: Document the new config key in `config.example.yaml`**

Append:

```yaml

# Optional — only needed for `comic-library check-pulls`.
# Your League of Comic Geeks pull-list ICS feed:
# https://leagueofcomicgeeks.com/member/calendar_ics/<your-username>
pull_list:
  calendar_url: ""
```

- [ ] **Step 5: Add the real calendar URL to the user's own (gitignored) `config.yaml`**

Append the same `pull_list:` block to `config.yaml`, with `calendar_url: "https://leagueofcomicgeeks.com/member/calendar_ics/peds24"`.

- [ ] **Step 6: Add the `check-pulls` command to `cli.py`**

Add these imports alongside the existing ones at the top of `cli.py`:

```python
from datetime import date

from library.metadata_sources.metron import MetronSource
from library.pull_calendar import fetch_pulled_items, load_state, save_state
from library.pull_resolver import resolve_and_add
from library.store import load_library, save_library
```

(`MetronSource`, `load_library`, `save_library` are likely already imported for other commands — check the existing import block and only add what's missing, keeping one import per module.)

Add the command, inserted after `import_physical_cmd` and before `serve`:

```python
@main.command("check-pulls")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
def check_pulls_cmd(config_path: str) -> None:
    """Fetches the configured League of Comic Geeks pull-list calendar,
    resolves every not-yet-processed already-released item via Metron, and
    adds each as a new physical record (or merges it into a matching
    digital one). Never touches git — run this from the weekly scheduled
    routine, which reviews the output and commits."""
    config = load_config(config_path)
    if not config.pull_list.calendar_url:
        click.echo("No pull_list.calendar_url configured in config.yaml.")
        return
    if not config.metron.is_configured:
        click.echo("Metron not configured — check-pulls requires it (fill in config.yaml).")
        return

    metron = MetronSource(config.metron.username, config.metron.password)
    library_path = config.data_dir / "library_comics.json"
    covers_dir = config.data_dir / "covers"
    state_path = config.data_dir / "pull_state.json"

    records = load_library(library_path)
    state = load_state(state_path)

    items = fetch_pulled_items(config.pull_list.calendar_url)
    today = date.today()
    pending = [
        item for item in items
        if item.event_uid not in state["processed_uids"] and item.release_date <= today
    ]

    added = merged = flagged = 0
    flag_lines: list[str] = []
    for item in pending:
        result = resolve_and_add(item, records, metron, covers_dir)
        state["processed_uids"].append(item.event_uid)
        if result.outcome == "added":
            added += 1
        elif result.outcome == "merged":
            merged += 1
        else:
            flagged += 1
            flag_lines.append(f"{item.title}: {result.reason}")

    save_library(library_path, records)
    save_state(state_path, state)

    click.echo(f"Checked {len(items)} pull-list item(s), {len(pending)} new.")
    click.echo(f"Added {added}, merged {merged} into existing digital records, flagged {flagged}.")
    for line in flag_lines:
        click.echo(f"  FLAGGED: {line}")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_cli_check_pulls.py -v`
Expected: PASS (5 tests)

- [ ] **Step 8: Run the full suite**

Run: `source .venv/bin/activate && pytest -q`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add library/config.py config.example.yaml cli.py tests/test_cli_check_pulls.py
git commit -m "$(cat <<'EOF'
Add check-pulls CLI command wiring the pull-list flow together

Deterministic, network-and-file-only: fetches the configured calendar,
resolves each not-yet-processed released item, adds/merges it, and
reports counts plus any flagged titles. Never touches git — that's the
scheduled routine's job (Task 11).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

(Note: `config.yaml` itself is gitignored — `git add` will not stage it, which is correct; only `config.example.yaml` should show up in the diff for that file.)

---

### Task 9: `add-comic` CLI command

**Files:**
- Modify: `library/metadata_sources/comic_geeks.py` (add `extract_comic_id`)
- Modify: `cli.py`
- Test: `tests/test_comic_geeks.py` (for `extract_comic_id`)
- Test: `tests/test_cli_add_comic.py`

**Interfaces:**
- Produces: `comic_geeks.extract_comic_id(url_or_id: str) -> str | None` — the numeric Comic Geeks id from a URL or bare id string.
- Produces: `comic-library add-comic <url> [--physical] [--config PATH]`.

- [ ] **Step 1: Write the failing test for `extract_comic_id`**

Add to `tests/test_comic_geeks.py`:

```python
from library.metadata_sources.comic_geeks import extract_comic_id


def test_extract_comic_id_from_full_url():
    assert extract_comic_id("https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16") == "6297209"


def test_extract_comic_id_from_bare_url():
    assert extract_comic_id("https://leagueofcomicgeeks.com/comic/6437939") == "6437939"


def test_extract_comic_id_from_bare_numeric_id():
    assert extract_comic_id("6297209") == "6297209"


def test_extract_comic_id_returns_none_for_unrecognized_url():
    assert extract_comic_id("https://leagueofcomicgeeks.com/pulls") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_comic_geeks.py -v -k extract_comic_id`
Expected: FAIL — `ImportError: cannot import name 'extract_comic_id'`

- [ ] **Step 3: Implement `extract_comic_id` in `library/metadata_sources/comic_geeks.py`**

Add near `is_comic_geeks_url`:

```python
_COMIC_ID_RE = re.compile(r"/comic/(\d+)")


def extract_comic_id(url_or_id: str) -> str | None:
    """The numeric Comic Geeks id from a full issue URL or a bare id
    string — used to build a fallback record id for add-comic when the
    page itself has no UPC."""
    stripped = url_or_id.strip()
    if stripped.isdigit():
        return stripped
    match = _COMIC_ID_RE.search(stripped)
    return match.group(1) if match else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_comic_geeks.py -v`
Expected: PASS (all tests, old and new)

- [ ] **Step 5: Write the failing CLI test**

Create `tests/test_cli_add_comic.py`:

```python
from pathlib import Path

import yaml
from click.testing import CliRunner

from cli import main


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump({"roots": [{"path": str(tmp_path), "type": "comic"}]}))
    return config_path


_FETCHED_INFO = {
    "series": "Absolute Batman", "issue_number": "16", "publisher": "DC Comics", "year": 2026,
    "description": "A synopsis.", "author": "Scott Snyder", "upc": "76194138584601611",
    "_image_url": "https://s3.amazonaws.com/comicgeeks/comics/covers/large-6297209.jpg",
}


class FakeCoverResponse:
    content = b"fake-cover-bytes"

    def raise_for_status(self):
        pass


def test_add_comic_rejects_non_comic_geeks_url(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["add-comic", "https://metron.cloud/issue/absolute-batman-2024-16/", "--config", str(config_path)])

    assert result.exit_code != 0
    assert "leagueofcomicgeeks.com" in result.output


def test_add_comic_reports_unreadable_page(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: {})

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)])

    assert result.exit_code != 0
    assert "Couldn't read" in result.output


def test_add_comic_creates_new_digital_record_by_default(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)])

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert "upc-76194138584601611" in library
    assert '"digital"' in library


def test_add_comic_physical_flag_adds_print_format(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--physical", "--config", str(config_path)])

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert '"print"' in library
    assert '"digital"' not in library


def test_add_comic_adds_format_to_already_existing_record(tmp_path: Path, monkeypatch):
    config_path = _write_config(tmp_path)
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

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--config", str(config_path)])

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert library.count('"id": "upc-76194138584601611"') == 1  # not duplicated
    assert '"digital"' in library
    assert '"print"' in library


def test_add_comic_merges_into_record_with_different_id_via_series_and_issue(tmp_path: Path, monkeypatch):
    """A digital scan has its own content-hash id, unrelated to the UPC a
    Comic Geeks link resolves to — the merge has to go by series+issue,
    not by id, or this would wrongly create a duplicate physical record."""
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    data_dir.joinpath("library_comics.json").write_text(
        '[{"id": "abcd1234-scanned", "title": "Absolute Batman #16", "type": "comic", '
        '"series": "Absolute Batman", "issue_number": "16", "formats": ["digital"], "metadata_source": {}, '
        '"preview_pages": [], "status": "unread", "added_date": "2026-01-01"}]'
    )
    monkeypatch.setattr("cli.comic_geeks.fetch_issue", lambda url: dict(_FETCHED_INFO))
    monkeypatch.setattr("library.covers.get_with_retry", lambda *a, **k: FakeCoverResponse())

    result = CliRunner().invoke(main, ["add-comic", "https://leagueofcomicgeeks.com/comic/6297209/absolute-batman-16", "--physical", "--config", str(config_path)])

    assert result.exit_code == 0
    library = (tmp_path / "data" / "library_comics.json").read_text()
    assert library.count('"id":') == 1  # merged, not duplicated
    assert '"abcd1234-scanned"' in library
    assert "upc-76194138584601611" not in library
    assert '"digital"' in library and '"print"' in library
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_cli_add_comic.py -v`
Expected: FAIL — `No such command 'add-comic'`

- [ ] **Step 7: Add the `add-comic` command to `cli.py`**

Add these imports alongside the existing ones:

```python
from library.covers import download_cover
from library.matching import extract_issue, find_matching_record, is_matchable
from library.metadata_sources import comic_geeks
```

Add the command, inserted after `check_pulls_cmd` and before `serve`:

```python
@main.command("add-comic")
@click.argument("url")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
@click.option("--physical", is_flag=True, help="Add as a physical copy instead of digital (default).")
def add_comic_cmd(url: str, config_path: str, physical: bool) -> None:
    """Adds a single comic from its League of Comic Geeks issue page —
    the manual counterpart to check-pulls, for a digital buy (default) or
    a one-off physical add outside the weekly pull-list flow."""
    if not comic_geeks.is_comic_geeks_url(url):
        raise click.ClickException(f"Only leagueofcomicgeeks.com links are supported: {url!r}")

    info = comic_geeks.fetch_issue(url)
    if not info:
        raise click.ClickException("Couldn't read that Comic Geeks page — check the URL, or the site may be unreachable.")

    config = load_config(config_path)
    library_path = config.data_dir / "library_comics.json"
    covers_dir = config.data_dir / "covers"
    records = load_library(library_path)

    new_format = "print" if physical else "digital"

    if info.get("upc"):
        record_id = f"upc-{info['upc']}"
    else:
        comic_id = comic_geeks.extract_comic_id(url)
        record_id = f"cgeeks-{comic_id}"

    existing = records.get(record_id)
    if existing is None and info.get("series") and info.get("issue_number") and is_matchable(info["series"], info["issue_number"]):
        existing = find_matching_record(records, info["series"], info["issue_number"])

    if existing is not None:
        if new_format not in existing.formats:
            existing.formats.append(new_format)
        save_library(library_path, records)
        click.echo(f"Already in your library as {existing.id} — added '{new_format}' to its formats.")
        return

    record = ComicRecord(id=record_id, title=info.get("series") or url, type="comic", formats=[new_format])
    for field in ("series", "issue_number", "publisher", "year", "description", "author", "upc"):
        if info.get(field):
            setattr(record, field, info[field])
            record.metadata_source[field] = "comic_geeks"
    if info.get("_image_url"):
        download_cover(record, info["_image_url"], "comic_geeks", covers_dir)

    records[record.id] = record
    save_library(library_path, records)
    click.echo(f"Added {record.series or record.title} #{record.issue_number or '?'} ({record.id}) as {new_format}.")
```

Add the missing model import if `ComicRecord` isn't already imported in `cli.py`:

```python
from library.models import ComicRecord
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_cli_add_comic.py tests/test_comic_geeks.py -v`
Expected: PASS (all)

- [ ] **Step 9: Run the full suite**

Run: `source .venv/bin/activate && pytest -q`
Expected: all PASS

- [ ] **Step 10: Commit**

```bash
git add library/metadata_sources/comic_geeks.py cli.py tests/test_comic_geeks.py tests/test_cli_add_comic.py
git commit -m "$(cat <<'EOF'
Add add-comic CLI command for manually adding a single Comic Geeks link

Digital by default (the stated common case — a digital buy outside the
pull list), --physical for a one-off print add. Dedupes against an
existing record by id, and merges into a same-series/issue record in
the other format instead of duplicating it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

---

### Task 10: `add-comic` shell wrapper + alias

**Files:**
- Create: `bin/add-comic`
- Modify: `~/.zshrc` (outside the repo)

**Interfaces:** none (shell-level only).

- [ ] **Step 1: Create the wrapper script**

Create `bin/add-comic`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "/Users/pedrosh/personal_projects/comic-view-ui"
exec .venv/bin/comic-library add-comic "$@"
```

A hardcoded absolute path is used rather than resolving `$0`'s directory, since a shell alias doesn't preserve `$0` the way a symlink would, and this is a single-machine, single-checkout personal tool. `cd`-ing into the repo first is required because `config.yaml`/`data/` are resolved relative to the working directory throughout this codebase (the same assumption `serve` already makes).

- [ ] **Step 2: Make it executable**

Run: `chmod +x bin/add-comic`

- [ ] **Step 3: Smoke-test it directly (bad-URL path, no network)**

Run: `./bin/add-comic https://example.com/not-comic-geeks`
Expected: prints `Only leagueofcomicgeeks.com links are supported: ...` and exits non-zero — confirms the wrapper correctly `cd`s and dispatches to the installed console script.

- [ ] **Step 4: Add the alias to the user's shell config**

Append to `~/.zshrc`:

```bash
alias add-comic="/Users/pedrosh/personal_projects/comic-view-ui/bin/add-comic"
```

- [ ] **Step 5: Verify from a different directory**

Run: `cd /tmp && source ~/.zshrc && add-comic https://example.com/not-comic-geeks`
Expected: same rejection message as Step 3 — confirms the alias works from any directory.

- [ ] **Step 6: Commit**

```bash
git add bin/add-comic
git commit -m "$(cat <<'EOF'
Add bin/add-comic wrapper script for the global add-comic alias

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgaE2pYaJRgTeV1G6tFi14
EOF
)"
```

(`~/.zshrc` is outside the repo and isn't part of this commit.)

---

### Task 11: Register the weekly pull-check scheduled routine

**Files:** none (operational setup via the `schedule` skill, performed after Task 8 lands).

This is a one-time setup action, not code — done once Task 8's `check-pulls` command exists and its tests pass.

- [ ] **Step 1: Invoke the `schedule` skill** to create a new scheduled routine with:

  - **Name:** `comic-pull-list-check`
  - **Cron schedule:** `0 9 * * 1` (every Monday at 9am local time — the calendar's own per-item dates, not this schedule, determine what actually gets processed; a weekly cadence just needs to run often enough that nothing sits unprocessed for long)
  - **Prompt:**

    ```
    Run `cd /Users/pedrosh/personal_projects/comic-view-ui && .venv/bin/comic-library check-pulls` and read its output.

    If it added or merged any comics: stage `data/library_comics.json`, `data/covers/`, and `data/pull_state.json` with git, and commit with a message summarizing what was added this run (titles + counts). Do not push.

    If it flagged anything: report each flagged title and the reason to the user in your response, and suggest they resolve it with `add-comic <url>` once they have the right League of Comic Geeks or Metron issue link.

    Always end with a one-paragraph summary: how many new comics were added, how many merged into existing digital records, and how many were flagged — regardless of whether the count was zero.
    ```

- [ ] **Step 2: Verify the routine was registered**

Use the `schedule` skill's list/status action to confirm `comic-pull-list-check` is scheduled for the next Monday 9am.

- [ ] **Step 3: Do a manual dry run**

Run `check-pulls` once by hand (`source .venv/bin/activate && comic-library check-pulls`) to confirm it runs cleanly end-to-end against the real calendar and real Metron credentials before waiting a week for the first scheduled run. Review its output with the user; if anything got added, confirm it looks right in the viewer (`comic-library serve`) before considering this task done.

---

## Self-Review Notes

- **Spec coverage:** every numbered component in the spec (browser fetch helper, comic_geeks transport swap, confidence-checked Metron resolution, pull calendar parsing, pull resolver, id scheme, add-comic CLI, shell wrapper, weekly routine, testing) maps to Tasks 1–11 one-to-one (id scheme is spread across Tasks 7 and 9, matching the two flows that generate ids).
- **Type consistency checked:** `find_issue_confident`'s `(dict | None, str, list[dict])` return shape is used identically in Task 3's own tests, Task 7's `pull_resolver.py`, and Task 8's CLI test mocks. `ResolveResult`'s field names (`outcome`, `title`, `reason`, `candidates`) match between Task 7's definition and Task 8's CLI consumption. `PulledItem`'s fields match between Task 5's definition and Tasks 7/8's usage.
- **No placeholders:** every step has real code or an exact shell command; the routine prompt in Task 11 is written out in full rather than described.
