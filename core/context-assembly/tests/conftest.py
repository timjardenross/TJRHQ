import sys
import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CA_DIR = _REPO_ROOT / "core" / "context-assembly"

if str(_CA_DIR) not in sys.path:
    sys.path.insert(0, str(_CA_DIR))


def _force_module(name: str, path: Path) -> None:
    """Load `path` and register it in sys.modules under `name`, overwriting
    whatever is already cached there under that name.

    Several unrelated parts of core/ ship a module with this same bare name
    (every core/infrastructure/* subsystem has its own config.py). Python
    caches modules by name process-wide, and some core/coordination/*.py
    modules insert other directories onto sys.path as an import
    side-effect — so when the full suite runs as one process
    (`pytest core/`), whichever subsystem's same-named module happens to
    be imported first wins for the rest of the run, silently breaking
    every other subsystem's `import config`. Forcing the correct module
    into sys.modules here, right before this subsystem's own tests
    collect, makes these tests correct regardless of what ran earlier in
    the same pytest process.
    """
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_force_module("config", _CA_DIR / "config.py")

# test_captain_brief_integration.py mocks platform-runtime/commands/captain_brief.py
# specifically (it patches cb_mod.urllib.request.urlopen) — but
# platform-runtime/lib/captain_brief.py is a second, unrelated module with the
# same bare name, and whichever one another test happens to import first wins
# process-wide for the same reason as above.
_force_module("captain_brief", _REPO_ROOT / "platform-runtime" / "commands" / "captain_brief.py")
