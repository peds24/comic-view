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


# Real-world scene/release naming patterns found in the library.


def test_volume_with_year_and_release_group_tags():
    result = parse_filename("Berserk v01 (2003) (Digital) (danke-Empire).cbz")
    assert result["series"] == "Berserk"
    assert result["year"] == 2003
    assert result["issue_number"] == "01"


def test_bracket_year_with_trailing_space_and_comma():
    result = parse_filename("Slam Dunk, v01 [1991] .cbz")
    assert result["series"] == "Slam Dunk"
    assert result["year"] == 1991
    assert result["issue_number"] == "01"


def test_bare_trailing_issue_with_year_and_release_group_tags():
    result = parse_filename("Absolute Batman 021 (2026) (Digital) (Lil-Empire).cbz")
    assert result["series"] == "Absolute Batman"
    assert result["year"] == 2026
    assert result["issue_number"] == "021"


def test_bare_trailing_issue_no_tags():
    result = parse_filename("Absolute Batman 01.cbr")
    assert result["series"] == "Absolute Batman"
    assert result["issue_number"] == "01"


def test_leading_batch_index_is_stripped():
    result = parse_filename("001 Batman 001 (7 covers) (2011) (Megan-Empire).cbr")
    assert result["series"] == "Batman"
    assert result["year"] == 2011
    assert result["issue_number"] == "001"


def test_multiple_noise_tags_all_stripped():
    result = parse_filename("Vagabond v02 (2008) (VIZBIG) (Scan) (HQ) (Colored Council).cbz")
    assert result["series"] == "Vagabond"
    assert result["year"] == 2008
    assert result["issue_number"] == "02"
