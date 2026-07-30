import sys
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _force_local_module(name: str) -> None:
    """Load <_ROOT>/<name>.py and register it in sys.modules under `name`,
    overwriting whatever is already cached there under that name.

    Several sibling subsystems under core/ each ship their own module with
    this same bare name (every core/infrastructure/* subsystem has its own
    config.py, and both this subsystem and core/health/ have their own
    supabase_client.py). Python caches modules by name process-wide, and
    some core/coordination/*.py modules insert other directories onto
    sys.path as an import side-effect — so when the full suite runs as one
    process (`pytest core/`), whichever subsystem's same-named module
    happens to be imported first wins for the rest of the run, silently
    breaking every other subsystem's `from <name> import ...`. Forcing the
    correct local module into sys.modules here, right before this
    subsystem's own tests collect, makes this subsystem's tests correct
    regardless of what ran earlier in the same pytest process.
    """
    path = _ROOT / f"{name}.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_force_local_module("config")
_force_local_module("supabase_client")
