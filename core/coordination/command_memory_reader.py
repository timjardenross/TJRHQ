#!/usr/bin/env python3
"""MSN-0053: minimal READ-ONLY adapter — live missions from Command Memory.

Wires Number One (MVP) to the operational Supabase `missions` table via the
same PostgREST + service-role pattern MSN-0051 validated. READ-ONLY: this module
issues only HTTP GET; it NEVER inserts/updates/deletes. No schema/DDL.

Replaces the stale JSON-file source for the MVP (MSN-0052 gap C2).
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any


def _load_env(env_path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    p = Path(env_path)
    if not p.exists():
        return env
    for line in p.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_live_missions(env_path: str = "slack-bot/.env", limit: int = 200) -> list[dict[str, Any]]:
    """Return live missions (list of dicts) from Command Memory. READ-ONLY (GET).

    Reads SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY from the environment, falling
    back to `env_path`. Returns [] (non-blocking) if creds/service unavailable.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        env = _load_env(env_path)
        url = url or env.get("SUPABASE_URL")
        key = key or env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        return []
    req = urllib.request.Request(
        f"{url}/rest/v1/missions?select=*&limit={int(limit)}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return []
