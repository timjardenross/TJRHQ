from pathlib import Path

import pytest
from src.parsing.brief_parser import parse_brief

SAMPLE_BRIEF_PATH = "examples/sample_brief.md"
SERVICE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _run_from_service_root(monkeypatch):
    """Tests use paths relative to the service (examples/...). CI invokes pytest
    from the repo root, so pin the cwd instead of depending on where it ran."""
    monkeypatch.chdir(SERVICE_ROOT)


@pytest.fixture
def brief():
    return parse_brief(SAMPLE_BRIEF_PATH)
