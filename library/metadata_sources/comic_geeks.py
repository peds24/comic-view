"""League of Comic Geeks (leagueofcomicgeeks.com) issue-page scraper.

No public API exists, and the site's Cloudflare rule blocks requests with
no/suspicious User-Agent header (confirmed live: a bare curl gets a 403
"Restricted" page, the same request with a normal browser User-Agent gets
a real 200) — unlike Metron's site, there's no JS challenge behind it, so
a plain GET with a browser-shaped User-Agent is enough to read the page.

Used only for a specific issue URL the user already has open in their
browser (see manual_attach.py) — there's no title/UPC search here, only
"fetch this exact page".
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from library import browser_fetch
from library.matching import extract_issue

_BASE_URL = "https://leagueofcomicgeeks.com"
_ISSUE_SUFFIX_RE = re.compile(r"\s*#\d+\s*$")


def is_comic_geeks_url(url: str) -> bool:
    return "leagueofcomicgeeks.com" in url


def _resolve_url(url_or_id: str) -> str:
    """Accepts a full issue URL, or a bare numeric id (the site resolves
    a slug-less /comic/<id> URL to the canonical page just fine)."""
    if url_or_id.strip().isdigit():
        return f"{_BASE_URL}/comic/{url_or_id.strip()}"
    return url_or_id


def _extract_writer(soup: BeautifulSoup) -> str | None:
    names = []
    for role_div in soup.select(".role"):
        roles = [r.strip().lower() for r in role_div.get_text(strip=True).split(",")]
        if "writer" not in roles:
            continue
        name_div = role_div.find_next_sibling("div", class_="name")
        if not name_div:
            continue
        link = name_div.find("a")
        name = (link or name_div).get_text(strip=True)
        if name:
            names.append(name)
    return ", ".join(dict.fromkeys(names)) if names else None


def _extract_year(soup: BeautifulSoup) -> int | None:
    """The "Released" date at the top of the page (when the issue
    actually shipped) is used, not the "Cover Date" detail field further
    down — matches the store_date-over-cover_date convention used
    elsewhere in this app."""
    header = soup.select_one(".header-intro")
    if not header:
        return None
    match = re.search(r"/comics/new-comics/(\d{4})/\d{2}/\d{2}", str(header))
    return int(match.group(1)) if match else None


def _extract_publisher(soup: BeautifulSoup) -> str | None:
    header = soup.select_one(".header-intro")
    if not header:
        return None
    link = header.find("a")
    return link.get_text(strip=True) if link else None


def _extract_upc(soup: BeautifulSoup) -> str | None:
    for block in soup.select(".details-addtl-block"):
        name = block.select_one(".name")
        value = block.select_one(".value")
        if name and value and name.get_text(strip=True).upper() == "UPC":
            return value.get_text(strip=True)
    return None


def _extract_cover_url(soup: BeautifulSoup) -> str | None:
    img = soup.select_one("a.cover-gallery img")
    if img and img.get("src"):
        return img["src"]
    meta = soup.select_one('meta[property="og:image"]')
    return meta["content"] if meta and meta.get("content") else None


def fetch_issue(url_or_id: str) -> dict:
    """Fetches a Comic Geeks issue page and returns a partial ComicRecord
    field dict (series/issue_number/author/publisher/year/description/upc,
    plus '_image_url' if a cover is available), or {} if the page can't be
    read."""
    resolved_url = _resolve_url(url_or_id)
    html = browser_fetch.fetch_html(resolved_url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    result: dict = {}

    h1 = soup.find("h1")
    if h1:
        page_title = h1.get_text(strip=True)
        issue_number = extract_issue(page_title)
        if issue_number:
            result["issue_number"] = issue_number
            series = _ISSUE_SUFFIX_RE.sub("", page_title).strip()
            if series:
                result["series"] = series

    publisher = _extract_publisher(soup)
    if publisher:
        result["publisher"] = publisher

    year = _extract_year(soup)
    if year:
        result["year"] = year

    description = soup.select_one(".listing-description p")
    if description and description.get_text(strip=True):
        result["description"] = description.get_text(strip=True)

    author = _extract_writer(soup)
    if author:
        result["author"] = author

    upc = _extract_upc(soup)
    if upc:
        result["upc"] = upc

    image_url = _extract_cover_url(soup)
    if image_url:
        result["_image_url"] = image_url

    return result
