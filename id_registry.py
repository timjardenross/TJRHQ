"""Central sequential ID registry for Starship Endeavour.

Generates human-typeable IDs: USS-TJR-MSN-0144, BREQ-0011, DEC-0001.
Thread-safe via an exclusive file lock. Falls back to a timestamp suffix on
I/O error so generation never blocks the caller.

Counter file: <repo-root>/.id-counters.json  (created on first use)
Seeds: counters start above the highest known existing IDs so new IDs
       never collide with legacy records.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
# _MINT_TEST_COUNTER lets the test suite point subprocesses at an isolated counter.
_COUNTER_FILE = Path(os.environ["_MINT_TEST_COUNTER"]) if "_MINT_TEST_COUNTER" in os.environ else _REPO_ROOT / ".id-counters.json"
_LOCK_FILE = _COUNTER_FILE.with_suffix(".lock")

# Start above the highest known existing IDs so we never collide with legacy records.
#   MSN: counter reconciled to 143 (Phase 0 audit, MSN-0064) → first new canonical ID is USS-TJR-MSN-0144
#   BREQ: 10 legacy timestamp-format BREQ files → first new ID is BREQ-0011
#   DEC: all legacy DECs are timestamp-format → first new ID is DEC-0001
_SEEDS: dict[str, int] = {
    "MSN": 143,
    "BREQ": 10,
    "DEC": 0,
}

# Prefixes that emit a full canonical form rather than the bare prefix.
# MSN-0064 Phase 1: MSN IDs now emit USS-TJR-MSN-NNNN (canonical per ADR-0001/MSN-0045).
# BREQ and DEC retain their short form.
_CANONICAL_PREFIX: dict[str, str] = {
    "MSN": "USS-TJR-MSN",
}


def _load() -> dict[str, int]:
    try:
        data = json.loads(_COUNTER_FILE.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in data.items() if isinstance(v, (int, float, str))}
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}


def _save(data: dict[str, int]) -> None:
    _COUNTER_FILE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def next_id(prefix: str) -> str:
    """Return the next sequential ID for prefix, e.g. next_id('MSN') → 'USS-TJR-MSN-0144'.

    Increments atomically under an exclusive file lock. On any I/O failure
    falls back to a microsecond timestamp suffix so callers never error out.
    MSN prefix emits the full canonical form USS-TJR-MSN-NNNN; other prefixes
    emit the short form (e.g. BREQ-0011, DEC-0001).
    """
    prefix = prefix.upper()
    canonical = _CANONICAL_PREFIX.get(prefix, prefix)
    try:
        _LOCK_FILE.touch(exist_ok=True)
        with open(_LOCK_FILE, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)  # blocks until acquired; auto-released on close
            data = _load()
            n = data.get(prefix, _SEEDS.get(prefix, 0)) + 1
            data[prefix] = n
            _save(data)
            return f"{canonical}-{n:04d}"
    except Exception:  # noqa: BLE001 — never let ID generation crash the caller
        from datetime import datetime
        return f"{canonical}-{datetime.now().strftime('%H%M%S%f')[:10]}"
