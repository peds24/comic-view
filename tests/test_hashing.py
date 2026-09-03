from pathlib import Path

from library.hashing import compute_id


def test_same_content_same_id_even_if_renamed(tmp_path: Path):
    original = tmp_path / "Batman #1.cbz"
    original.write_bytes(b"comic archive bytes" * 100)

    renamed = tmp_path / "renamed.cbz"
    renamed.write_bytes(original.read_bytes())

    assert compute_id(original) == compute_id(renamed)


def test_different_content_different_id(tmp_path: Path):
    a = tmp_path / "a.cbz"
    a.write_bytes(b"aaaa")
    b = tmp_path / "b.cbz"
    b.write_bytes(b"bbbb")

    assert compute_id(a) != compute_id(b)
