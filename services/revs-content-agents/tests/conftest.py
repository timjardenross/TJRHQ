from pathlib import Path

import pytest
from src.parsing.brief_parser import parse_brief

# Absolute, so the suite passes whatever the cwd is: CI runs pytest from the
# repo root (python-ci.yml), local runs often happen from this directory.
SAMPLE_BRIEF_PATH = str(Path(__file__).resolve().parent.parent / "examples" / "sample_brief.md")


@pytest.fixture
def brief():
    return parse_brief(SAMPLE_BRIEF_PATH)
