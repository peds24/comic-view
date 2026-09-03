from library.models import ComicRecord


def test_from_dict_defaults_formats_to_digital_when_absent():
    """Records saved before the `formats` field existed load without a migration step."""
    old_shape = {
        "id": "abc123",
        "title": "Old Comic",
        "type": "comic",
    }
    record = ComicRecord.from_dict(old_shape)
    assert record.formats == ["digital"]


def test_from_dict_respects_explicit_formats():
    record = ComicRecord.from_dict({
        "id": "abc123",
        "title": "Physical Comic",
        "type": "comic",
        "formats": ["print"],
    })
    assert record.formats == ["print"]
