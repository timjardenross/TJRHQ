"""LLM access for the Telegram agent — single source of truth is platform-runtime/llm.py.

Rather than fork the provider logic (Gemini -> Ollama -> OpenAI auto-fallback),
we import the existing, battle-tested module by adding the platform-runtime dir to
sys.path. That module is pure-stdlib and standalone, so the import is clean.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SLACK_BOT_LLM = _REPO_ROOT / "platform-runtime" / "llm.py"

# NOTE: this module is itself named ``llm``. A plain ``from llm import ...`` (even
# after putting platform-runtime on sys.path) resolves to *this* partially-initialized
# module via sys.modules and raises a circular-import ImportError. Load the
# platform-runtime module by file path under a distinct name to sidestep the collision.
# platform-runtime/llm.py is pure-stdlib and standalone, so this is a clean load.
try:  # pragma: no cover - exercised in deploy, not unit tests
    _spec = importlib.util.spec_from_file_location("slack_bot_llm", _SLACK_BOT_LLM)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"cannot load spec for {_SLACK_BOT_LLM}")
    _slack_llm = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_slack_llm)
    _ask_commander_safe = _slack_llm.ask_commander_safe
    _is_llm_configured = _slack_llm.is_llm_configured
    _IMPORT_ERROR = ""
except Exception as exc:  # keep the agent importable even if platform-runtime is absent
    _ask_commander_safe = None
    _is_llm_configured = None
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


def is_configured() -> bool:
    if _is_llm_configured is None:
        return False
    try:
        return bool(_is_llm_configured())
    except Exception:
        return False


def ask(system_prompt: str, user_prompt: str) -> tuple[bool, str]:
    """Return (ok, text). Never raises — mirrors ask_commander_safe semantics."""
    if _ask_commander_safe is None:
        return False, f"LLM module unavailable ({_IMPORT_ERROR or 'platform-runtime/llm.py not found'})"
    return _ask_commander_safe(system_prompt, user_prompt)
