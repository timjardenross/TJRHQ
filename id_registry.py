"""Central sequential ID registry for Starship Endeavour.

Generates human-typeable IDs: USS-TJR-MSN-0144, BREQ-0011, DEC-0001.
Thread-safe via an exclusive file lock. Falls back to a timestamp suffix on
I/O error so generation never blocks the caller.

Counter file: <repo-root>/.id-counters.json  (created on first use)
Seeds: counters start above the highest known existing IDs so new IDs
       never collide with legacy records.

Self-healing collision check (2026-08-10, mission-ID-minting-durable-fix):
the counter file had drifted from reality (been manually reconciled 4+
times, and was found entirely missing from a checkout the same night this
was built -- see .id-counters.json's own git history). next_id() now scans
the repo (and, for prefixes with a live Supabase table, the table) for the
true highest in-use number before allocating, and auto-bumps the stored
counter if it's behind -- logging loudly when it does, so drift-correction
stays visible rather than silently masked. See tools/id_counter_drift_check.py
for the read-only version of the same check, meant for mission close-out.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

_log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent

try:  # optional convenience for standalone/manual invocation; never a hard dependency
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass
# _MINT_TEST_COUNTER lets the test suite point subprocesses at an isolated counter.
_COUNTER_FILE = Path(os.environ["_MINT_TEST_COUNTER"]) if "_MINT_TEST_COUNTER" in os.environ else _REPO_ROOT / ".id-counters.json"
_LOCK_FILE = _COUNTER_FILE.with_suffix(".lock")

# Start above the highest known existing IDs so we never collide with legacy records.
#   MSN: counter reconciled to 143 (Phase 0 audit, MSN-0064) → first new canonical ID is USS-TJR-MSN-0144
#   BREQ: 10 legacy timestamp-format BREQ files → first new ID is BREQ-0011
#   DEC: all legacy DECs are timestamp-format → first new ID is DEC-0001
#
# 2026-07-05 (Phase 0 stabilisation): the live counter (.id-counters.json, not this
# seed) was reconciled from 206 to 209 — platform-runtime/commands/mission_brief.py had an
# independent, non-delegating minting path (Supabase MAX(id)+1, querying the wrong
# "id" UUID column instead of "mission_id", silently always falling through to a
# stale mission-index.txt) that had drifted ~25 IDs behind this registry. It now
# delegates to next_id("MSN") like every other caller; the seed above is unaffected.
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

# All prefixes this registry mints. Used by the collision-check scan and by
# tools/id_counter_drift_check.py to know what to check.
KNOWN_PREFIXES: tuple[str, ...] = ("MSN", "BREQ", "DEC")

# Live Supabase table backing a prefix's real allocations, as {prefix: (table, column)}.
# Verified 2026-08-10: `missions.mission_id` is the real MSN store. BREQ/DEC have no
# equivalent live table today -- `build_request_inbox.request_id` uses an unrelated
# ("AI-<ACTION>-<timestamp>-<rand>") ID scheme, and `decisions` is keyed by mission_id,
# not a DEC id, so neither belongs here. Re-check if that ever changes.
_TABLE_SCAN: dict[str, tuple[str, str]] = {
    "MSN": ("missions", "mission_id"),
}

# Collision-check repo scan scope: same file types the 2026-08-10 manual
# reconciliation used (.md/.py/.ts/.tsx/.json).
_SCAN_INCLUDE_GLOBS: tuple[str, ...] = ("*.md", "*.py", "*.ts", "*.tsx", "*.json")
_SCAN_EXCLUDE_DIRS: tuple[str, ...] = (
    "node_modules", ".git", ".next", ".venv", "__pycache__", "dist", "build",
    "tests", "__tests__",
)
_SCAN_EXCLUDE_FILES: tuple[str, ...] = (
    "test_*.py", "*_test.py", "*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx",
    # The ID-minting infrastructure's own docs/CLI/tests carry illustrative
    # example IDs (e.g. "USS-TJR-MSN-0148" in tools/MISSION-MINTING.md) that
    # are not real allocations -- exclude them so an example never poses as
    # a true max.
    "id_registry.py", "mint_id.py", "mint_server.py", "test_mint.py",
    "MISSION-MINTING.md", "id_counter_drift_check.py",
)


def scan_repo_max(prefix: str) -> tuple[int, str | None]:
    """Best-effort repo-wide scan for the highest in-use N in `{prefix}-NNNN`
    (matches both bare and canonical forms, e.g. MSN-0148 or USS-TJR-MSN-0148,
    since the canonical form contains the bare form as a substring).

    Read-only, shells out to `grep` for speed (a few hundred ms across the
    whole repo). Returns (0, None) on any failure -- never raises, so a
    broken/missing `grep` degrades to "no scan signal found", not a crash.
    """
    pattern = rf"\b{re.escape(prefix)}-[0-9]{{4,5}}\b"
    cmd = ["grep", "-rhoE", pattern]
    for glob in _SCAN_INCLUDE_GLOBS:
        cmd += ["--include", glob]
    for d in _SCAN_EXCLUDE_DIRS:
        cmd.append(f"--exclude-dir={d}")
    for f in _SCAN_EXCLUDE_FILES:
        cmd.append(f"--exclude={f}")
    cmd.append(str(_REPO_ROOT))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception as exc:
        _log.debug("id_registry: repo scan failed for %s: %s", prefix, exc)
        return 0, None
    best_n, best_hit = 0, None
    for line in result.stdout.splitlines():
        match = re.search(r"([0-9]{4,5})$", line)
        if not match:
            continue
        n = int(match.group(1))
        if n > best_n:
            best_n, best_hit = n, line
    return best_n, best_hit


def scan_table_max(prefix: str) -> int | None:
    """Best-effort Supabase lookup of the highest real ID for `prefix`, for
    prefixes with a live table registered in _TABLE_SCAN. Returns None if no
    table is configured for this prefix, Supabase env vars aren't set, or the
    query fails for any reason -- never raises, never blocks minting.
    """
    table_col = _TABLE_SCAN.get(prefix)
    if table_col is None:
        return None
    table, column = table_col
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        params = urllib.parse.urlencode({"select": column, column: f"like.*{prefix}-*"})
        req = urllib.request.Request(
            f"{url}/rest/v1/{table}?{params}",
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — best-effort scan, never blocks minting
        _log.debug("id_registry: table scan failed for %s (%s.%s): %s", prefix, table, column, exc)
        return None
    # Trailing \b matters: without it, a legacy timestamp-format ID like
    # "MSN-20260613-102725" would greedily match "20260" as if it were a real
    # 5-digit sequence number. The \b forces the digit run to actually end
    # there (fails to match inside a longer digit run), so legacy/timestamp
    # IDs are correctly skipped rather than misread as a huge true max.
    num_re = re.compile(rf"{re.escape(prefix)}-([0-9]{{4,5}})\b")
    best_n = 0
    for row in rows if isinstance(rows, list) else []:
        match = num_re.search(str(row.get(column) or ""))
        if match:
            best_n = max(best_n, int(match.group(1)))
    return best_n or None


def true_max_for_prefix(prefix: str) -> tuple[int, str, str] | None:
    """Combine the repo scan and (where configured) the live table into the
    single highest in-use number found for `prefix`, with provenance for
    logging/reporting. Returns None if neither signal found anything above 0.
    """
    prefix = prefix.upper()
    candidates: list[tuple[int, str, str]] = []
    grep_n, grep_hit = scan_repo_max(prefix)
    if grep_n:
        candidates.append((grep_n, "repo scan", grep_hit or "(no matching line)"))
    live_n = scan_table_max(prefix)
    if live_n:
        table, column = _TABLE_SCAN[prefix]
        candidates.append((live_n, "Supabase", f"{table}.{column}"))
    if not candidates:
        return None
    return max(candidates, key=lambda c: c[0])


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

    Collision check: before allocating, scans the repo (and the live table
    for prefixes that have one) for the true highest in-use number. If the
    stored counter is behind, it's auto-bumped to match and a warning is
    logged -- so a stale/missing counter file self-heals instead of minting
    a colliding ID. The scan runs outside the lock (read-only, no need to
    serialise it); only the bump-and-increment is done under the lock.
    """
    prefix = prefix.upper()
    canonical = _CANONICAL_PREFIX.get(prefix, prefix)
    scan_result = true_max_for_prefix(prefix)  # best-effort; never raises
    try:
        _LOCK_FILE.touch(exist_ok=True)
        with open(_LOCK_FILE, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)  # blocks until acquired; auto-released on close
            data = _load()
            stored = data.get(prefix, _SEEDS.get(prefix, 0))
            if scan_result and scan_result[0] > stored:
                true_max, source, detail = scan_result
                _log.warning(
                    "id_registry: counter drift detected for %s -- stored=%s true_max=%s "
                    "(source=%s, %s). Auto-bumping counter before minting.",
                    prefix, stored, true_max, source, detail,
                )
                data[prefix] = true_max
            n = data.get(prefix, _SEEDS.get(prefix, 0)) + 1
            data[prefix] = n
            _save(data)
            return f"{canonical}-{n:04d}"
    except Exception:  # noqa: BLE001 — never let ID generation crash the caller
        from datetime import datetime
        return f"{canonical}-{datetime.now().strftime('%H%M%S%f')[:10]}"
