"""Collision-safe sibling import for tools/paperclip/*.py.

client.py here shares its bare filename with tools/supabase/client.py — a
`sys.path.insert` + bare `import client` picks up whichever one happened
to load first in the process, for the rest of that process (Fleet
Engineering Review 2026-08-11). Mirrors tools/supabase/_local_import.py —
see that file's docstring for the full story.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent


def import_sibling(name: str) -> ModuleType:
    """Import tools/paperclip/{name}.py under a collision-safe key."""
    unique_key = f"_tools_paperclip_local__{name}"
    cached = sys.modules.get(unique_key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(unique_key, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load tools/paperclip/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_key] = module
    spec.loader.exec_module(module)
    return module
