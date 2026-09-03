"""Best-effort metadata extraction from a comic's filename.

Used only to fill fields ComicInfo.xml didn't provide. Handles common
scene/release conventions seen in the wild, e.g.:

  Batman (2019) #003.cbz                              -> series, year, issue
  Berserk v01 (2003) (Digital) (danke-Empire).cbz      -> series, year, issue
  Slam Dunk, v01 [1991] .cbz                           -> series, year, issue
  Absolute Batman 021 (2026) (Digital) (Lil-Empire).cbz -> series, year, issue
  001 Batman 001 (7 covers) (2011) (Megan-Empire).cbr  -> series, year, issue
  Plain Title.cbz                                      -> title only

Any parenthesized/bracketed group left after the year is pulled out is
treated as release-group noise (quality tags, scanlation group names, "X
covers", etc.) and stripped — enumerating every group name that shows up in
the wild isn't tractable, so this strips generically instead.
"""
from __future__ import annotations

import re

_YEAR_RE = re.compile(r"[(\[](?P<year>19\d{2}|20\d{2})[)\]]")
_BRACKET_GROUP_RE = re.compile(r"\s*[(\[][^()\[\]]*[)\]]")
# Leading zero-padded batch/order index some scene releases prefix files
# with, e.g. "001 Batman 001 ...". Stripped unconditionally — real comic
# titles essentially never start with a bare number + space (rare
# exceptions like "100 Bullets" are a known, accepted trade-off).
_LEADING_BATCH_INDEX_RE = re.compile(r"^\d{1,4}\s+")
_HASH_ISSUE_RE = re.compile(r"#(?P<issue>\d+)")
_VOLUME_RE = re.compile(r"\bv(?:ol(?:ume)?)?\.?\s*(?P<issue>\d+)\b", re.IGNORECASE)
_TRAILING_ISSUE_RE = re.compile(r"[-,]?\s*(?P<issue>\d{1,4})\s*$")


def parse_filename(filename: str) -> dict:
    """Returns a partial dict of ComicRecord fields."""
    stem = filename
    for ext in (".cbz", ".cbr"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    stem = stem.strip()

    remainder = _LEADING_BATCH_INDEX_RE.sub("", stem)

    result: dict = {}

    year_match = _YEAR_RE.search(remainder)
    if year_match:
        result["year"] = int(year_match.group("year"))
        remainder = remainder[: year_match.start()] + remainder[year_match.end():]

    remainder = _BRACKET_GROUP_RE.sub("", remainder)
    remainder = re.sub(r"\s{2,}", " ", remainder)

    issue_match = _HASH_ISSUE_RE.search(remainder)
    if not issue_match:
        issue_match = _VOLUME_RE.search(remainder)
    if not issue_match:
        issue_match = _TRAILING_ISSUE_RE.search(remainder)

    if issue_match:
        result["issue_number"] = issue_match.group("issue")
        remainder = remainder[: issue_match.start()] + remainder[issue_match.end():]

    series = remainder.strip(" -_.,")
    series = re.sub(r"\s{2,}", " ", series)
    if series:
        result["series"] = series
        result["title"] = series
    else:
        result["title"] = stem

    return result
