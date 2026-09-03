"""Best-effort metadata extraction from a comic's filename.

Used only to fill fields ComicInfo.xml didn't provide. Handles common
conventions:

  Series Name (2019) #003.cbz        -> series, year, issue_number
  Series Name (2019).cbz             -> series, year
  Series Name v01.cbz                -> series, issue_number
  Series Name - 001.cbr              -> series, issue_number
  Plain Title.cbz                    -> title only
"""
from __future__ import annotations

import re

_YEAR_RE = re.compile(r"\((?P<year>19\d{2}|20\d{2})\)")
_ISSUE_HASH_RE = re.compile(r"#(?P<issue>\d+)")
_VOLUME_RE = re.compile(r"\bv(?:ol(?:ume)?)?\.?\s*(?P<issue>\d+)\b", re.IGNORECASE)
_TRAILING_ISSUE_RE = re.compile(r"-\s*(?P<issue>\d+)\s*$")


def parse_filename(filename: str) -> dict:
    """Returns a partial dict of ComicRecord fields."""
    stem = filename
    for ext in (".cbz", ".cbr"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    stem = stem.strip()

    result: dict = {}
    remainder = stem

    year_match = _YEAR_RE.search(remainder)
    if year_match:
        result["year"] = int(year_match.group("year"))
        remainder = remainder[: year_match.start()] + remainder[year_match.end():]

    issue_match = _ISSUE_HASH_RE.search(remainder)
    if issue_match:
        result["issue_number"] = issue_match.group("issue")
        remainder = remainder[: issue_match.start()] + remainder[issue_match.end():]
    else:
        vol_match = _VOLUME_RE.search(remainder)
        if vol_match:
            result["issue_number"] = vol_match.group("issue")
            remainder = remainder[: vol_match.start()] + remainder[vol_match.end():]
        else:
            trailing_match = _TRAILING_ISSUE_RE.search(remainder)
            if trailing_match:
                result["issue_number"] = trailing_match.group("issue")
                remainder = remainder[: trailing_match.start()]

    series = remainder.strip(" -_.")
    series = re.sub(r"\s{2,}", " ", series)
    if series:
        result["series"] = series
        result["title"] = series
    else:
        result["title"] = stem

    return result
