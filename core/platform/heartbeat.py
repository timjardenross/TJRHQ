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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def record_heartbeat(
    domain_key: str,
    status: str = "ok",
    detail: Optional[str] = None,
    error_message: Optional[str] = None,
    latency_ms: Optional[int] = None,
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
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        log.warning("record_heartbeat(%s) write failed: %s", domain_key, exc)
        return False


def record_heartbeat_ok(domain_key: str, detail: Optional[str] = None, latency_ms: Optional[int] = None) -> bool:
    """Convenience wrapper for the common case."""
    return record_heartbeat(domain_key, status="ok", detail=detail, latency_ms=latency_ms)


def record_heartbeat_failed(domain_key: str, error_message: str) -> bool:
    """Convenience wrapper for a failed run attempt."""
    return record_heartbeat(domain_key, status="failed", error_message=error_message)


def supabase_get(path: str, timeout: int = 10) -> List[Dict[str, Any]]:
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"Supabase GET error {exc.code}: {body}") from exc

    parsed = json.loads(body)
    return parsed if isinstance(parsed, list) else [parsed]


def supabase_insert(table: str, payload: Dict[str, Any], timeout: int = 10) -> bool:
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
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return False
