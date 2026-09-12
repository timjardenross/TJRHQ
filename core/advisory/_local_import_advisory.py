"""Collision-safe sibling import for core/advisory/*.py.

core/advisory/*.py files cross-import each other by bare module name
(`import outcomes`, not `from . import outcomes`) — deliberate, since
several of these are also runnable directly as scripts (core/advisory/
cli.py has a __main__ entry point), and a plain relative import fails
with "attempted relative import with no known parent package" when a
module is executed directly rather than imported as part of the package.

The cost: at least 11 filenames here collide with same-named files
elsewhere in the repo (escalation.py also in intelligence/workflow/,
forecast.py also in platform-runtime/lib/delivery/, learning.py also in
platform-runtime/lib/human_systems/, lessons.py and patterns.py also in
platform-runtime/lib/learning/, operating_picture.py also in core/
intelligence/, opportunities.py also in platform-runtime/lib/comms/,
outcomes.py also in platform-runtime/lib/strategy/, service.py also in
intelligence/workflow/, cli.py also in intelligence/workflow/ and two
core/infrastructure/ directories, daily_brief.py also in platform-
runtime/lib/). Python caches modules by bare name for the life of a
process, so whichever same-named file loads first wins for every import
after it — this produced real, confirmed test failures (Fleet
Engineering Review 2026-08-11: AttributeError against the wrong module,
surfacing only in full multi-file pytest sessions, never when a file
runs alone).

import_sibling() loads a same-directory module under a directory-
qualified, collision-proof sys.modules key instead of relying on
sys.path order + a bare import — works identically whether the caller
is run directly as a script or imported as part of a larger chain, and
can never collide with a same-named file anywhere else in the process.
Mirrors tools/supabase/_local_import_supabase.py and tools/paperclip/
_local_import_paperclip.py — see either for the pattern this follows.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent


def import_sibling(name: str) -> ModuleType:
    """Import core/advisory/{name}.py under a collision-safe key."""
    unique_key = f"_core_advisory_local__{name}"
    cached = sys.modules.get(unique_key)
    if cached is not None:
        return cached
    return _load(name, unique_key)


def reload_sibling(name: str) -> ModuleType:
    """Force a fresh re-execution of core/advisory/{name}.py, same as
    importlib.reload() but on the collision-safe key — for tests (e.g. the
    advisory suite's `seeded` fixture) that intentionally re-run a module's
    top-level code between tests to pick up fresh env-derived state
    (ADVISORY_DATA_ROOT). A plain import_sibling() call only ever loads
    once; this always re-executes.

    Mutates the existing cached module object in place (exec_module into
    it directly) rather than creating a new one, matching real
    importlib.reload()'s own semantics — other already-loaded modules
    that hold a reference to this one (e.g. service.py's own
    `_outcomes = import_sibling("outcomes")`) see the refreshed state
    automatically, without needing their own reload, because it's the
    same object. Creating a fresh module object instead would silently
    orphan every such cross-reference."""
    unique_key = f"_core_advisory_local__{name}"
    return _load(name, unique_key)


def _load(name: str, unique_key: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(unique_key, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load core/advisory/{name}.py")
    module = sys.modules.get(unique_key)
    if module is None:
        module = importlib.util.module_from_spec(spec)
        sys.modules[unique_key] = module
    spec.loader.exec_module(module)
    return module
