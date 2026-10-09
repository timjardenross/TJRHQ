"""Supabase Free-plan database size: one line for the weekly report plus a
once-a-day warning guard (USS-TJR-MSN-0412 Stream 4).

The Free plan turns the database read-only at 500 MB. It sat at 83.8% before
Stream 4, and nothing told the Captain it was creeping toward the limit. This
module has two jobs, both reusing existing paths (no new scheduler):

  * format_line() / fetch_size_mb(): the "Supabase DB: X MB of 500 MB (Y%)"
    line that generate_weekly_report() renders.
  * check_and_warn(): called from send_brief() on the morning brief (the one
    brief that runs every day). At or above WARN_THRESHOLD_MB it sends one
    WARNING through core.platform.notification_service.notify(), at most once
    per WARN_COOLDOWN_SECONDS, using the same Telegram path every other alert
    uses.

The size comes from the read-only RPC public.get_db_size_bytes() (migration
0230), because pg_database_size() is not reachable through PostgREST tables.
Everything here is best-effort: a failed size check never breaks a brief, and
the weekly line says "size unavailable" instead of silently disappearing.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

DB_LIMIT_MB = 500
WARN_THRESHOLD_MB = 450
WARN_COOLDOWN_SECONDS = 24 * 60 * 60

# Runtime state (gitignored: data/alert_state/ holds the other alert cooldowns).
_STATE_PATH = Path(os.environ.get("DB_SIZE_WARN_STATE", "/opt/starship-endeavour/data/alert_state/db_size_warning.json"))


def fetch_size_mb() -> float | None:
    """Current database size in MB via the get_db_size_bytes() RPC, or None if
    the size cannot be read (unconfigured, RPC missing, network failure)."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        log.warning("db_size: Supabase not configured (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY unset)")
        return None
    req = urllib.request.Request(
        f"{url}/rest/v1/rpc/get_db_size_bytes",
        data=b"{}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:  # nosec B310 - url is built from the SUPABASE_URL env var, always https (same as captains_brief._sb_request)
            return int(json.loads(resp.read())) / 1048576
    except Exception as exc:  # noqa: BLE001 - best-effort size check; the caller degrades the line, never the brief
        log.warning("db_size: could not read database size: %s", exc)
        return None


def format_line(size_mb: float | None) -> str:
    """The weekly-report line. Never empty: a failed check says so."""
    if size_mb is None:
        return "🗄 Supabase DB: size unavailable (check failed)"
    pct = round(100 * size_mb / DB_LIMIT_MB)
    flag = "⚠️ " if size_mb >= WARN_THRESHOLD_MB else ""
    return f"🗄 {flag}Supabase DB: {size_mb:.0f} MB of {DB_LIMIT_MB} MB ({pct}%)"


def _last_warned(path: Path) -> float | None:
    try:
        return float(json.loads(path.read_text()).get("last_warned"))
    except Exception:  # noqa: BLE001 - missing/corrupt state means "never warned", which errs toward warning
        return None


def _record_warning(path: Path, size_mb: float, now: float) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last_warned": now, "size_mb": round(size_mb, 1)}))
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001 - failing to record only risks a repeat warning
        log.warning("db_size: could not record warning state: %s", exc)


def check_and_warn(
    size_mb: float | None = None,
    *,
    now: float | None = None,
    notify_fn: Callable[..., object] | None = None,
    state_path: Path | None = None,
) -> bool:
    """Warn once per cooldown when the database is at or above the threshold.
    Returns True only if a warning was sent. Never raises."""
    try:
        size = fetch_size_mb() if size_mb is None else size_mb
        if size is None or size < WARN_THRESHOLD_MB:
            return False
        now = time.time() if now is None else now
        path = state_path or _STATE_PATH
        last = _last_warned(path)
        if last is not None and (now - last) < WARN_COOLDOWN_SECONDS:
            return False
        if notify_fn is None:
            from core.platform.notification_service import Severity, notify

            # local adapter: the shared sender, at WARNING severity
            def notify_fn(body: str, **kw: object) -> object:
                return notify(body, severity=Severity.WARNING, **kw)

        pct = round(100 * size / DB_LIMIT_MB)
        body = (
            f"Supabase database is {size:.0f} MB of {DB_LIMIT_MB} MB ({pct}%), at or above the "
            f"{WARN_THRESHOLD_MB} MB warning line. The Free plan turns the database read-only at "
            f"{DB_LIMIT_MB} MB."
        )
        result = notify_fn(body, title="Supabase database size")
        if getattr(result, "ok", True) is False:
            log.error("db_size: warning send failed: %s", getattr(result, "error", "unknown"))
            return False
        _record_warning(path, size, now)
        return True
    except Exception as exc:  # noqa: BLE001 - the size guard must never break a brief
        log.warning("db_size: check_and_warn failed: %s", exc)
        return False
