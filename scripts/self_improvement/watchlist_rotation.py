"""
Persistence for HQ Evolution watchlist topic rotation (2026-09-25 review
follow-up to external_discovery.py).

external_discovery.discover() needs to know, across cycles, which
watchlist topic was searched least recently so it can rotate stalest-first
instead of always favouring the first N topics in the file. That state
lives here rather than in config/evolution_watchlist.json itself: the
watchlist is operator-maintained config (diffed and read by humans), while
this is cycle bookkeeping the orchestrator owns — same separation the
codebase already uses for data/self-improvement/review/finding_staleness.jsonl
and opportunity_id_counter.txt.

Fails open like every other piece of this pipeline: a missing or corrupt
state file means "nothing has ever been searched" (empty dict), never a
failed cycle.
"""

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("watchlist_rotation")


def load_rotation_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data: Any = json.load(f)
        if not isinstance(data, dict):
            log.warning(f"Rotation state at {path} is not a JSON object — ignoring")
            return {}
        return {str(k): str(v) for k, v in data.items()}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(f"Failed to load rotation state at {path}: {exc}")
        return {}


def save_rotation_state(path: Path, state: dict[str, str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        tmp_path.replace(path)
    except OSError as exc:
        # Rotation is best-effort bookkeeping, not correctness-critical:
        # worst case on a write failure is the next cycle re-deriving the
        # same stalest-first order from the last state that did persist.
        log.warning(f"Failed to save rotation state at {path}: {exc}")
