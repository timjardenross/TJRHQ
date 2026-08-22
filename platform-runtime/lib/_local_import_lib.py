"""Collision-safe sibling import for platform-runtime/lib/*.py.

daily_brief.py here shares its bare filename with core/advisory/
daily_brief.py — two test files (test_daily_brief_interrupt_now.py,
test_outcome_capture.py) each want THIS one specifically, but a bare
`import daily_brief` after a sys.path insert picks up whichever same-
named file happened to load first in the process (Fleet Engineering
Review 2026-08-11). Mirrors core/advisory/_local_import_advisory.py and
tools/supabase/_local_import_supabase.py — see either for the pattern.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent


def import_sibling(name: str) -> ModuleType:
    """Import platform-runtime/lib/{name}.py under a collision-safe key."""
    unique_key = f"_platform_runtime_lib_local__{name}"
    cached = sys.modules.get(unique_key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(unique_key, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load platform-runtime/lib/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_key] = module
    spec.loader.exec_module(module)
    return module
