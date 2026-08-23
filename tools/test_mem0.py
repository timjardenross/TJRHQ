#!/usr/bin/env python3
"""Smoke test for the mem0 backend wired into unified_memory.

Adds a test memory, searches for it, and exits 0 on success.
Run from the repo root with the platform-runtime venv:

    /opt/starship-endeavour/platform-runtime/.venv/bin/python3 tools/test_mem0.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make the repo root importable so core.platform.unified_memory resolves.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("test_mem0")


def _load_dotenv() -> None:
    """Load key=value pairs from .env into os.environ (no third-party dependency)."""
    import os
    env_path = _REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    _load_dotenv()
    from core.platform.unified_memory import MemoryType, recall, remember

    test_text = "Captain prefers concise briefs under 200 words"
    test_user = "captain"
    search_query = "brief length preferences"

    log.info("Adding test memory: %r (user_id=%r)", test_text, test_user)
    add_result = remember(MemoryType.SEMANTIC, test_text, user_id=test_user)

    if not add_result:
        log.error(
            "remember() returned empty — mem0 backend may be unavailable. "
            "Check GEMINI_API_KEY is set and mem0ai is installed."
        )
        return 1

    log.info("add result: %s", add_result)

    log.info("Searching for: %r", search_query)
    search_results = recall(MemoryType.SEMANTIC, query=search_query, user_id=test_user)

    if not search_results:
        log.error("recall() returned no results after add — search may have failed.")
        return 1

    log.info("Search returned %d result(s):", len(search_results))
    for i, result in enumerate(search_results, start=1):
        memory_text = result.get("memory") or result.get("text") or str(result)
        score = result.get("score")
        score_str = f" (score={score:.3f})" if score is not None else ""
        print(f"  [{i}]{score_str} {memory_text}")

    log.info("test_mem0: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
