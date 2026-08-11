"""Collision-safe sibling import for tools/supabase/*.py.

Several file names in this directory (supabase_client.py, embedding_client.py,
client.py) are also used by unrelated files elsewhere in the repo (e.g.
core/health/supabase_client.py). Every module here that needs a sibling used
to do `import supabase_client` after inserting this directory at the front
of sys.path — works fine in isolation, but Python caches modules by their
bare name for the life of the process: whichever same-named file gets
imported first anywhere in that process wins for every import after it,
including in unrelated tests that expect a *different* file. That
collision hung/broke a chunk of tests/ tests before this existed (Fleet
Engineering Review 2026-08-11) whenever an advisory-pipeline test ran in
the same pytest session as one needing a different supabase_client.py.

import_sibling() loads a same-directory module under a directory-qualified
unique key instead of the bare filename, so it can never collide with a
same-named file anywhere else in the process, regardless of import order —
and works identically whether the caller is run directly as a script or
imported as part of a larger chain.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent


def import_sibling(name: str) -> ModuleType:
    """Import tools/supabase/{name}.py under a collision-safe key."""
    unique_key = f"_tools_supabase_local__{name}"
    cached = sys.modules.get(unique_key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(unique_key, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load tools/supabase/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_key] = module
    spec.loader.exec_module(module)
    return module
