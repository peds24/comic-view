import subprocess
from pathlib import Path

import pytest

from library.git_utils import commit_if_changed


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)


def test_commit_if_changed_commits_a_new_file(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data.json").write_text('{"a": 1}')

    committed = commit_if_changed(["data.json"], "Add data.json")

    assert committed is True
    log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "Add data.json" in log.stdout


def test_commit_if_changed_returns_false_when_nothing_changed(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data.json").write_text('{"a": 1}')
    commit_if_changed(["data.json"], "Initial")

    committed = commit_if_changed(["data.json"], "No-op")

    assert committed is False


def test_commit_if_changed_does_not_sweep_in_unrelated_staged_changes(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.json").write_text("{}")
    subprocess.run(["git", "add", "a.json", "b.json"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True)

    (tmp_path / "b.json").write_text('{"unrelated": true}')
    subprocess.run(["git", "add", "b.json"], cwd=tmp_path, check=True)  # staged, unrelated to this call

    (tmp_path / "a.json").write_text('{"a": "changed"}')
    committed = commit_if_changed(["a.json"], "Update a.json")

    assert committed is True
    status = subprocess.run(["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "M  b.json" in status.stdout  # still staged, not swept into our commit
    log = subprocess.run(["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert "Update a.json" in log.stdout


def test_commit_if_changed_raises_when_not_a_git_repo(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data.json").write_text("{}")

    with pytest.raises(subprocess.CalledProcessError):
        commit_if_changed(["data.json"], "test")
