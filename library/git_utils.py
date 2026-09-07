"""Tiny local-commit helper for CLI commands that make their own edits to
the library (add-comic, check-pulls) — commits locally right after a
successful run. Never pushes; that stays a manual, reviewed action."""
from __future__ import annotations

import subprocess


def commit_if_changed(paths: list[str], message: str) -> bool:
    """Stages `paths` and commits `message` if that would actually change
    anything. Returns True if a commit was made, False if there was
    nothing to commit (paths already match HEAD).

    Both the staged-diff check and the commit itself are scoped to
    `paths` via a trailing pathspec, so any other file a caller happens to
    already have staged is left untouched rather than swept into this
    commit."""
    subprocess.run(["git", "add", *paths], check=True, capture_output=True, text=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--", *paths])
    if staged.returncode == 0:
        return False
    subprocess.run(["git", "commit", "-m", message, "--", *paths], check=True, capture_output=True, text=True)
    return True
