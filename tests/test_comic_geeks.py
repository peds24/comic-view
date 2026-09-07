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
