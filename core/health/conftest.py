import sys
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def _force_module(name: str, path: Path) -> None:
    """Load `path` and register it in sys.modules under `name`, overwriting
    whatever is already cached there under that name.

    core/infrastructure/vm-processing/ ships its own, unrelated
    supabase_client.py. Python caches modules by name process-wide, so when
    the full suite runs as one process (`pytest core/`), whichever
    subsystem's same-named module happens to be imported first wins for the
    rest of the run — silently breaking every other subsystem's
    `from supabase_client import ...`. Forcing the correct module into
    sys.modules here, right before this package's own tests collect, makes
    these tests correct regardless of what ran earlier in the same pytest
    process.
    """
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_force_module("supabase_client", _ROOT / "supabase_client.py")
