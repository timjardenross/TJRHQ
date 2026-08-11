import pytest

from src.parsing.brief_parser import parse_brief


def test_parses_real_brief(brief):
    assert brief.concept_id == "REC-001"
    assert brief.status == "Production-Ready"
    assert brief.target_audiences == ["Individual", "Therapist (with framing notes)"]
    assert brief.headline.startswith("You Are Not One Problem")
    assert len(brief.sections) == 5
    assert brief.sections[0].word_target == 200
    assert brief.sections[0].title == "WHAT ARE THE 12 SYSTEMS?"
    assert brief.closing_title == "THE PROMISE"
    assert "real change begins" in brief.closing_body


def test_missing_concept_id_raises(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("# Title\n## Sub\nNo metadata block here.\n")
    with pytest.raises(ValueError, match="Concept ID"):
        parse_brief(bad)


def test_no_section_headers_raises(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("# Title\nJust a paragraph, no headers at all.\n")
    with pytest.raises(ValueError, match="section headers"):
        parse_brief(bad)
