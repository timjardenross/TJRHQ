"""
Supabase client for the health intelligence modules.

Thin stdlib-only wrapper around PostgREST.
Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from environment.
Falls back to .env file at repo root if environment variables are unset.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# .env loader (no third-party deps)
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Load key=value pairs from repo-root .env into os.environ (no-op if already set)."""
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def supabase_get(path: str, timeout: int = 10) -> List[Dict[str, Any]]:
    """
    GET /rest/v1/{path} and return parsed JSON list.
    Raises RuntimeError on HTTP error or missing credentials.
    """
    url, key = _URL, _KEY
    if not url or not key:
        raise RuntimeError("Supabase credentials not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)")

    full_url = f"{url.rstrip('/')}/rest/v1/{path}"
    req = urllib.request.Request(
        full_url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
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


def supabase_upsert(
    table: str,
    payload: Dict[str, Any],
    on_conflict: str,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    POST with Prefer: resolution=merge-duplicates to upsert a row.
    Returns the upserted row.
    """
    url, key = _URL, _KEY
    if not url or not key:
        raise RuntimeError("Supabase credentials not configured")

    full_url = f"{url.rstrip('/')}/rest/v1/{table}?on_conflict={urllib.parse.quote(on_conflict)}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        full_url,
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"Supabase upsert error {exc.code}: {detail}") from exc

    return result[0] if isinstance(result, list) else result


def supabase_insert(
    table: str,
    payload: Dict[str, Any],
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    POST to insert a new row (no conflict handling).
    Returns the inserted row.
    Use supabase_upsert() when idempotency on a conflict column is required.
    """
    url, key = _URL, _KEY
    if not url or not key:
        raise RuntimeError("Supabase credentials not configured")

    full_url = f"{url.rstrip('/')}/rest/v1/{table}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        full_url,
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"Supabase insert error {exc.code}: {detail}") from exc

    return result[0] if isinstance(result, list) else result


def is_configured() -> bool:
    return bool(_URL and _KEY)
