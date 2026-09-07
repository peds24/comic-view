"""Load and validate config.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class RootConfig:
    path: Path
    type: str  # "comic" | "manga"


@dataclass
class MetronConfig:
    username: str = ""
    password: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.username and self.password)


@dataclass
class GoogleBooksConfig:
    api_key: str = ""


@dataclass
class PullListConfig:
    calendar_url: str = ""


@dataclass
class Config:
    roots: list[RootConfig]
    metron: MetronConfig
    google_books: GoogleBooksConfig
    data_dir: Path
    pull_list: PullListConfig


def load_config(config_path: str | Path, data_dir: str | Path = "data") -> Config:
    config_path = Path(config_path)
    raw = yaml.safe_load(config_path.read_text()) or {}

    roots = []
    for entry in raw.get("roots", []):
        roots.append(
            RootConfig(
                path=Path(entry["path"]).expanduser().resolve(),
                type=entry["type"],
            )
        )
    if not roots:
        raise ValueError(f"No 'roots' configured in {config_path}")
    for root in roots:
        if root.type not in ("comic", "manga"):
            raise ValueError(f"Root {root.path} has invalid type '{root.type}' (expected 'comic' or 'manga')")

    metron_raw = raw.get("metron", {}) or {}
    google_raw = raw.get("google_books", {}) or {}
    pull_list_raw = raw.get("pull_list", {}) or {}

    return Config(
        roots=roots,
        metron=MetronConfig(
            username=metron_raw.get("username", ""),
            password=metron_raw.get("password", ""),
        ),
        google_books=GoogleBooksConfig(api_key=google_raw.get("api_key", "")),
        data_dir=Path(data_dir),
        pull_list=PullListConfig(calendar_url=pull_list_raw.get("calendar_url", "")),
    )
