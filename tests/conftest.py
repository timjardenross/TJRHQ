"""Test isolation for the advisory runtime.

The advisory outcome store (core/advisory/outcomes.py) reads ADVISORY_DATA_ROOT
at call time. Point it at a throwaway temp dir for the whole test session so
tests can record advice/outcomes without ever writing into the committed repo.

Per-test fixtures may still override this with monkeypatch.setenv.
"""

import os
import tempfile
from pathlib import Path

_TEST_ADVISORY_ROOT = Path(tempfile.gettempdir()) / "usstjros-advisory-tests"
os.environ.setdefault("ADVISORY_DATA_ROOT", str(_TEST_ADVISORY_ROOT))
