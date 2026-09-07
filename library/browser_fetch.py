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
