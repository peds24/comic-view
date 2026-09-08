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
