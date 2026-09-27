"""Domain heartbeat writer (STARSHIP-REDESIGN.md §4 verification engine).

Thin stdlib-only wrapper around PostgREST, matching the same idiom already
used by core/health/supabase_client.py and core/coordination/command_bus.py's
private senders. Deliberately self-contained (no import of another
core.* module's Supabase client) so any scheduler/job in the repo can add
a single `record_heartbeat(...)` call at its success point without taking
on a new cross-module dependency.

Every domain registered in domain_registry (migration 0071) writes here on
each run attempt. Internal jobs are domains too, per spec §4.1 - this module
has no special case for "internal" vs "external", it is the one mechanism.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("heartbeat")


def _load_dotenv() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    try:
        if not env_path.exists():
            return
        content = env_path.read_text(encoding="utf-8")
    except OSError:
        # Not readable by this process (e.g. root-owned 0600 .env, service
        # running as a non-root user) — fine, the vars may already be in
        # os.environ via systemd's EnvironmentFile= (read by root before
        # the user switch). A heartbeat helper must never break import for
        # the job it's attached to; see record_heartbeat's own contract.
        return
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()

_URL = os.environ.get("SUPABASE_URL", "")
_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


# ── Healthy-heartbeat throttle (Supabase usage review 2026-09-27) ──────────
# Every run of every job wrote a heartbeat row, including jobs on 5-min
# cadences that report "ok" all day (~2k PostgREST writes/day). Staleness
# (domain_heartbeat_latest.is_stale) only needs a *recent* ok, so a repeated
# healthy heartbeat is written at most every _OK_MIN_INTERVAL_SECONDS per
# domain. Always written immediately: any 'failed', and any status change
# (e.g. failed -> ok recovery). Domains whose cadence+grace window is shorter
# than this interval plus one cycle had their window widened in migration
# 0227. Exempt: verification_engine (core/platform/deadmans_switch.py derives
# its alarm window from that domain's registry row) and intelligence_collection
# (intelligence/brief/morning_cycle.py needs a heartbeat since local midnight;
# it's a daily job so throttling it saves nothing anyway).
# State is a small local JSON file shared by every process on the host; it
# is only updated after a successful write, so a lost/raced update can only
# ever cause an extra write, never a skipped one. Set the interval to 0 to
# disable throttling.
_OK_MIN_INTERVAL_SECONDS = int(os.environ.get("HEARTBEAT_OK_MIN_INTERVAL_SECONDS", "1200"))
_THROTTLE_EXEMPT = frozenset({"verification_engine", "intelligence_collection"})
_THROTTLE_STATE_PATH = Path(os.environ.get(
    "HEARTBEAT_THROTTLE_STATE",
    str(Path(__file__).resolve().parents[2] / "outputs" / ".heartbeat_throttle.json"),
))


def _read_throttle_state() -> dict[str, Any]:
    try:
        data = json.loads(_THROTTLE_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _should_write(domain_key: str, status: str, state: dict[str, Any], now: float) -> bool:
    if _OK_MIN_INTERVAL_SECONDS <= 0 or status == "failed" or domain_key in _THROTTLE_EXEMPT:
        return True
    last = state.get(domain_key)
    if not isinstance(last, dict) or last.get("status") != status:
        return True
    try:
        return now - float(last.get("at", 0)) >= _OK_MIN_INTERVAL_SECONDS
    except (TypeError, ValueError):
        return True


def _remember_writes(rows: list[tuple[str, str]], now: float) -> None:
    """Record successful writes. Best effort: an unwritable state file just
    means the next heartbeat for these domains is written too."""
    try:
        state = _read_throttle_state()
        for domain_key, status in rows:
            state[domain_key] = {"status": status, "at": now}
        _THROTTLE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _THROTTLE_STATE_PATH.with_name(f"{_THROTTLE_STATE_PATH.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, _THROTTLE_STATE_PATH)
    except OSError as exc:
        log.debug("heartbeat throttle state not saved: %s", exc)


def record_heartbeat(
    domain_key: str,
    status: str = "ok",
    detail: str | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
    timeout: int = 10,
) -> bool:
    """Record one run attempt for `domain_key` into domain_heartbeats.

    Returns True on success, False on any failure (never raises) - a
    heartbeat write must never be able to break the job it's attached to.
    `status` must be one of 'ok' | 'failed' | 'skipped' (matches the
    domain_heartbeats CHECK constraint from migration 0071).
    """
    if status not in ("ok", "failed", "skipped"):
        status = "failed"

    now = time.time()
    if not _should_write(domain_key, status, _read_throttle_state(), now):
        return True  # a recent identical healthy heartbeat already covers this run

    if not _URL or not _KEY:
        log.warning(
            "record_heartbeat(%s): SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set "
            "in this process's environment — heartbeat silently dropped", domain_key,
        )
        return False

    payload = {
        "domain_key": domain_key,
        "status": status,
        "detail": detail,
        "error_message": error_message,
        "latency_ms": latency_ms,
    }
    body = json.dumps(payload).encode("utf-8")
    url = f"{_URL.rstrip('/')}/rest/v1/domain_heartbeats"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "apikey": _KEY,
            "Authorization": f"Bearer {_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout):  # nosec B310 - url is built from SUPABASE_URL env var, always https - reviewed 2026-09-12
            pass
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        log.warning("record_heartbeat(%s) write failed: %s", domain_key, exc)
        return False
    _remember_writes([(domain_key, status)], now)
    return True


def record_heartbeats(rows: list[dict[str, Any]], timeout: int = 10) -> bool:
    """Record several run attempts in one POST (a JSON array insert) — for a
    job that runs many domains per tick (e.g. the emergency-alert hub's ~15
    sources every 15 min), one request instead of one per domain. Each row
    takes record_heartbeat()'s keyword arguments. Never raises."""
    now = time.time()
    state = _read_throttle_state()
    payload = []
    for row in rows:
        status = row.get("status") if row.get("status") in ("ok", "failed", "skipped") else "failed"
        if not _should_write(row["domain_key"], status, state, now):
            continue
        payload.append({
            "domain_key": row["domain_key"],
            "status": status,
            "detail": row.get("detail"),
            "error_message": row.get("error_message"),
            "latency_ms": row.get("latency_ms"),
        })
    if not payload:
        return True
    if not _URL or not _KEY:
        log.warning("record_heartbeats: SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set — %d heartbeat(s) dropped", len(payload))
        return False
    req = urllib.request.Request(
        f"{_URL.rstrip('/')}/rest/v1/domain_heartbeats",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "apikey": _KEY,
            "Authorization": f"Bearer {_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout):  # nosec B310 - url is built from SUPABASE_URL env var, always https - reviewed 2026-09-12
            pass
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        log.warning("record_heartbeats(%d rows) write failed: %s", len(payload), exc)
        return False
    _remember_writes([(row["domain_key"], row["status"]) for row in payload], now)
    return True


def record_heartbeat_ok(domain_key: str, detail: str | None = None, latency_ms: int | None = None) -> bool:
    """Convenience wrapper for the common case."""
    return record_heartbeat(domain_key, status="ok", detail=detail, latency_ms=latency_ms)


def record_heartbeat_failed(domain_key: str, error_message: str) -> bool:
    """Convenience wrapper for a failed run attempt."""
    return record_heartbeat(domain_key, status="failed", error_message=error_message)


def supabase_get(path: str, timeout: int = 10) -> list[dict[str, Any]]:
    """GET /rest/v1/{path}. Raises RuntimeError on HTTP error or missing credentials."""
    if not _URL or not _KEY:
        raise RuntimeError("Supabase credentials not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)")

    url = f"{_URL.rstrip('/')}/rest/v1/{path}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": _KEY,
            "Authorization": f"Bearer {_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - url is built from SUPABASE_URL env var, always https - reviewed 2026-09-12
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"Supabase GET error {exc.code}: {body}") from exc

    parsed = json.loads(body)
    return parsed if isinstance(parsed, list) else [parsed]


def supabase_insert(table: str, payload: dict[str, Any], timeout: int = 10) -> bool:
    """POST one row to /rest/v1/{table}. Returns True on success, never raises."""
    if not _URL or not _KEY:
        return False
    body = json.dumps(payload).encode("utf-8")
    url = f"{_URL.rstrip('/')}/rest/v1/{table}"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "apikey": _KEY,
            "Authorization": f"Bearer {_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout):  # nosec B310 - url is built from SUPABASE_URL env var, always https - reviewed 2026-09-12
            return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return False
