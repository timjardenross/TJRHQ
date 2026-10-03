"""
platform-runtime pytest conftest.

Points id_registry's counter at a per-test tmp file so tests that mint IDs
through the real registry (e.g. log_decision_to_command_memory() -> next_id("DEC")
in test_command_memory.py) never mutate the tracked <repo-root>/.id-counters.json.
id_registry resolves _COUNTER_FILE/_LOCK_FILE at import time, so patch the module
attributes directly -- same approach as tools/test_mint.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import id_registry  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_id_counter(tmp_path, monkeypatch):
    counter_file = tmp_path / ".id-counters.json"
    monkeypatch.setattr(id_registry, "_COUNTER_FILE", counter_file)
    monkeypatch.setattr(id_registry, "_LOCK_FILE", counter_file.with_suffix(".lock"))
    yield counter_file
