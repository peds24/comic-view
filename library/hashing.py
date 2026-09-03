"""Stable content-based IDs for comic files.

We deliberately hash file content rather than storing a path, so a renamed or
moved file is still recognized as the same comic on rescan, and the library
never needs to keep a reference back to where a file lives on disk.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

_PARTIAL_HASH_BYTES = 1024 * 1024  # 1MB is enough to distinguish comics cheaply


def compute_id(path: Path) -> str:
    size = path.stat().st_size
    sha1 = hashlib.sha1()
    with path.open("rb") as f:
        sha1.update(f.read(_PARTIAL_HASH_BYTES))
    return f"{size:x}-{sha1.hexdigest()[:16]}"
