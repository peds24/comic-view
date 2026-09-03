"""Data model for a single comic/manga entry in the library."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Literal

ComicType = Literal["comic", "manga"]
ReadStatus = Literal["read", "unread"]


@dataclass
class ComicRecord:
    id: str
    title: str
    type: ComicType
    series: str | None = None
    issue_number: str | None = None
    author: str | None = None
    year: int | None = None
    publisher: str | None = None
    description: str | None = None
    isbn: str | None = None
    cover_path: str | None = None
    preview_pages: list[str] = field(default_factory=list)
    status: ReadStatus = "unread"
    # "digital", "physical", or both — defaults to ["digital"] so records
    # saved before this field existed still load correctly.
    formats: list[str] = field(default_factory=lambda: ["digital"])
    added_date: str = field(default_factory=lambda: date.today().isoformat())
    metadata_source: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ComicRecord":
        return cls(**data)

    def missing_fields(self) -> list[str]:
        """Fields worth trying to fill in via online enrichment."""
        fields_to_check = ("title", "author", "year", "publisher", "description")
        return [f for f in fields_to_check if not getattr(self, f)]

    def apply_partial(self, partial: dict, source: str) -> None:
        """Fill in only the fields that are currently empty, from a lower-priority source."""
        for key, value in partial.items():
            if value in (None, "", []):
                continue
            if not getattr(self, key, None):
                setattr(self, key, value)
                self.metadata_source[key] = source
