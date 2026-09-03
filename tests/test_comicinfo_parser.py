from library.comicinfo_parser import parse_comicinfo

SAMPLE_XML = b"""<?xml version="1.0"?>
<ComicInfo>
  <Title>The Long Halloween #1</Title>
  <Series>Batman: The Long Halloween</Series>
  <Number>1</Number>
  <Publisher>DC Comics</Publisher>
  <Year>1996</Year>
  <Summary>Harvey Dent asks Batman, Gordon, and Falcone for help.</Summary>
  <Writer>Jeph Loeb</Writer>
  <Penciller>Tim Sale</Penciller>
</ComicInfo>
"""


def test_parses_all_known_fields():
    result = parse_comicinfo(SAMPLE_XML)
    assert result["title"] == "The Long Halloween #1"
    assert result["series"] == "Batman: The Long Halloween"
    assert result["issue_number"] == "1"
    assert result["publisher"] == "DC Comics"
    assert result["year"] == 1996
    assert result["description"].startswith("Harvey Dent")
    assert result["author"] == "Jeph Loeb"


def test_missing_tags_are_omitted():
    result = parse_comicinfo(b"<ComicInfo><Title>Just A Title</Title></ComicInfo>")
    assert result == {"title": "Just A Title"}


def test_malformed_xml_returns_empty():
    assert parse_comicinfo(b"not xml") == {}
