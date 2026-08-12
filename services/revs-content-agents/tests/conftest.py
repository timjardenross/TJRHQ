import pytest

from src.parsing.brief_parser import parse_brief

SAMPLE_BRIEF_PATH = "examples/sample_brief.md"


@pytest.fixture
def brief():
    return parse_brief(SAMPLE_BRIEF_PATH)
