from library.filename_parser import parse_filename


def test_series_year_and_issue_hash():
    result = parse_filename("Batman (2019) #003.cbz")
    assert result["series"] == "Batman"
    assert result["year"] == 2019
    assert result["issue_number"] == "003"


def test_series_and_year_only():
    result = parse_filename("Saga (2012).cbz")
    assert result["series"] == "Saga"
    assert result["year"] == 2012
    assert "issue_number" not in result


def test_series_with_volume():
    result = parse_filename("One Piece v01.cbz")
    assert result["series"] == "One Piece"
    assert result["issue_number"] == "01"


def test_series_with_trailing_dash_number():
    result = parse_filename("Berserk - 001.cbr")
    assert result["series"] == "Berserk"
    assert result["issue_number"] == "001"


def test_plain_title_only():
    result = parse_filename("Watchmen.cbz")
    assert result["title"] == "Watchmen"
    assert "year" not in result
    assert "issue_number" not in result
