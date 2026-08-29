"""Command Operations Bus — cross-service routing and health orchestration.

Polls Supabase and systemd state on a configurable cycle, detects problems,
self-heals where safe, and routes alerts to the Captain across Slack and
Telegram.  This is the thin coordination layer that was previously missing —
it does not replace individual service polling, it coordinates across them.

Routing rules (applied every COMMAND_BUS_INTERVAL seconds, default 300):
  1. executor_stuck       — build_request_inbox row stuck at engineering_running
                            > EXECUTOR_STUCK_MIN minutes → ALERT
  2. service_health       — critical services down or HTTP backend unhealthy → ALERT
  3. new_missions         — newly created Idea-status missions → one-time triage nudge

# 2026-08-29 (decommissioning-discipline drift check): removed the
# "executor_needs_restart" rule and its telegram-build-executor.service
# restart/alert path. That service was retired in d98a4207 (this session,
# dead Telegram approval pipeline removal) but this watchdog kept trying
# to restart it and alerting on every cycle — the watcher wasn't
# decommissioned alongside the thing it watched. The legacy telegram-
# sourced approved rows it was guarding (action_type IS NULL, no
# execution-attempt record) are handled honestly by
# build_request_verifier.py instead; see its docstring for why "not found
# downstream" is reported rather than a fabricated "failed".

Outputs:
  Slack    — all alerts (CAPTAINS_INBOX_CHANNEL_ID or BRIEF_CHANNEL from platform-runtime/.env)
  Telegram — ALERT/CRITICAL severity (TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_CHAT_IDS)

State: SQLite at outputs/command_bus.db

CLI:
  python -m core.coordination.command_bus run    # start the polling loop
  python -m core.coordination.command_bus once   # run one cycle and exit (debugging)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from core.platform.notification_service import Severity, Transport
from core.platform.notification_service import notify as _notify

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = REPO_ROOT / "outputs"

# ---------------------------------------------------------------------------
# Config (env vars, with .env fallback)
# ---------------------------------------------------------------------------

# 2026-08-29: migrated onto core/platform/configuration_service.py's
# load_dotenv_files() (see tools/check_config_loaders.py) — bulk-loads once
# at import instead of re-reading the .env files from disk on every _env()
# call. Also drops two stale fallback paths (telegram-bot/.env, xo-bot/.env)
# that no longer exist — the actual directories are telegram-bots/xo/.env
# etc., neither of which this file ever needed (TELEGRAM_BOT_TOKEN already
# lives in platform-runtime/.env).
from core.platform.configuration_service import load_dotenv_files

load_dotenv_files([REPO_ROOT / ".env", REPO_ROOT / "platform-runtime" / ".env"])


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


_INTERVAL           = int(_env("COMMAND_BUS_INTERVAL", "300"))       # seconds between cycles
_STUCK_MIN          = int(_env("EXECUTOR_STUCK_MIN", "60"))           # minutes before stuck alert
_NOTIFY_COOLDOWN_H  = int(_env("COMMAND_BUS_NOTIFY_COOLDOWN_H", "4")) # hours between repeat alerts

_SLACK_TOKEN        = _env("SLACK_BOT_TOKEN")
_SLACK_CHANNEL      = _env("BRIEF_CHANNEL") or _env("BRIEF_USER_ID") or _env("CAPTAINS_INBOX_CHANNEL_ID")
_TG_TOKEN           = _env("TELEGRAM_BOT_TOKEN")
_TG_CHAT_ID         = (_env("TELEGRAM_ALLOWED_CHAT_IDS") or "").split(",")[0].strip()

_BACKEND_HEALTH_URL = _env("BACKEND_HEALTH_URL", "http://localhost:5000/health")

# Services and their criticality (only services we care about monitoring).
_SERVICES = {
    # starfleet-slack-bot.service and starfleet-backend.service retired 2026-08-23.
    # Both are disabled/inactive — backend's working-dir.conf points to a
    # non-existent archive path; slack-bot superseded by XO bot (tg-xo.service).
    # Removed from monitoring to stop phantom CRITICAL alerts.
    "tg-xo.service":                    "HIGH",
    # tg-engineer / tg-engineering-dept retired 2026-07-05 (XO is the only
    # Telegram bot). Removed from monitoring so their permanent-down state
    # stops raising phantom HIGH alerts.
    # MSN-0330: found unmonitored by audit — Captain Intelligence's
    # Insight/Reasoning Engines depend on this being up (MSN-0329
    # Phase 3-5); wasn't in this dict at all before.
    "model-router.service":            "HIGH",
}

# ---------------------------------------------------------------------------
# State DB
# ---------------------------------------------------------------------------

_DB_PATH = OUTPUTS_DIR / "command_bus.db"


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bus_events (
            event_key     TEXT PRIMARY KEY,
            first_seen    TEXT NOT NULL,
            last_notified TEXT,
            last_action   TEXT,
            notif_count   INTEGER DEFAULT 0,
            action_count  INTEGER DEFAULT 0,
            resolved_at   TEXT
        );
        CREATE TABLE IF NOT EXISTS seen_missions (
            mission_id TEXT PRIMARY KEY,
            first_seen TEXT NOT NULL
        );
    """)
    conn.commit()


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        yield conn
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _upsert_event(conn: sqlite3.Connection, key: str) -> sqlite3.Row:
    now = _now_iso()
    conn.execute(
        "INSERT OR IGNORE INTO bus_events (event_key, first_seen) VALUES (?, ?)",
        (key, now),
    )
    conn.commit()
    return conn.execute("SELECT * FROM bus_events WHERE event_key=?", (key,)).fetchone()


def _should_notify(row: sqlite3.Row, cooldown_hours: int) -> bool:
    if row["notif_count"] == 0:
        return True
    if not row["last_notified"]:
        return True
    last = datetime.fromisoformat(row["last_notified"])
    return (datetime.now(timezone.utc) - last) >= timedelta(hours=cooldown_hours)


def _mark_notified(conn: sqlite3.Connection, key: str) -> None:
    conn.execute(
        "UPDATE bus_events SET last_notified=?, notif_count=notif_count+1 WHERE event_key=?",
        (_now_iso(), key),
    )
    conn.commit()


def _resolve_if_gone(conn: sqlite3.Connection, key: str) -> bool:
    """Returns True only if this call actually flipped an open event to
    resolved (a real recovery transition) — False for a no-op on an
    already-resolved or never-open key. MSN-0330: this distinction is
    what lets the caller emit exactly one core_events row per real
    transition, not one per 300s poll cycle."""
    cur = conn.execute(
        "UPDATE bus_events SET resolved_at=? WHERE event_key=? AND resolved_at IS NULL",
        (_now_iso(), key),
    )
    conn.commit()
    return cur.rowcount > 0


def _reopen_event(conn: sqlite3.Connection, key: str) -> None:
    conn.execute(
        "UPDATE bus_events SET resolved_at=NULL WHERE event_key=?", (key,)
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Routing outputs
# ---------------------------------------------------------------------------

def _slack(message: str) -> bool:
    if not _SLACK_TOKEN or not _SLACK_CHANNEL:
        log.warning("[bus:slack] No Slack token/channel configured")
        return False
    payload = json.dumps({"channel": _SLACK_CHANNEL, "text": message}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={"Authorization": f"Bearer {_SLACK_TOKEN}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.load(r)
            if not resp.get("ok"):
                log.warning("[bus:slack] API error: %s", resp.get("error"))
                return False
        return True
    except Exception as exc:
        log.error("[bus:slack] Request failed: %s", exc)
        return False


def _esc_html(value: object) -> str:
    """Escape a DYNAMIC value for Telegram's HTML parse_mode, before it's
    interpolated into `tg` — the Telegram-bound message string, which mixes
    intentional <b>/<code> HTML with runtime values. `msg` (the Slack-bound
    string built alongside `tg` at each call site) intentionally does NOT
    use this — Slack was never affected by the bug this exists for, and
    its own mrkdwn (*bold*) formatting is unrelated to Telegram's parser.

    2026-08-22, corrected same day: this used to escape for legacy
    Telegram "Markdown" parse_mode (backslash before _, *, `, [). That
    stopped an HTTP 400 hard-reject on unescaped underscores (real risk in
    this file: req_id, svc, and _restart_executor()'s raw error detail can
    all plausibly contain underscores) — but real-device verification
    showed the backslashes render as LITERAL visible characters, not
    consumed as escapes; legacy Markdown's escaping does not behave the
    way it was assumed to. Switched to Telegram's HTML parse_mode instead
    (see core/platform/notification_service.py's matching fix and its
    _escape_telegram_html docstring for the full story) — HTML only needs
    &, <, > escaped, no ambiguity.

    Still required after the notification_service cutover below: _route()
    sends via notify(..., template="raw"), which does NOT escape the body
    for us (that would double-escape these already-escaped values). This
    file remains the one place responsible for escaping its own dynamic
    Telegram-bound content."""
    text = str(value)
    for ch, esc in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;")):
        text = text.replace(ch, esc)
    return text


_SEVERITY_MAP = {
    "CRITICAL": Severity.CRITICAL,
    "ALERT": Severity.ALERT,
    "HIGH": Severity.ALERT,
    "MEDIUM": Severity.WARNING,
}


def _route(severity: str, slack_msg: str, tg_msg: str | None = None) -> bool:
    """Post to Slack (always) and Telegram (ALERT/CRITICAL). Returns True if Slack succeeded.

    2026-08-22 Wave 2 cutover: sends now go through
    notification_service.notify() instead of this file's own raw
    urllib senders (_slack/_telegram have been retired from this path —
    notification_service owns retry/backoff and the call-log now).
    template="raw" is deliberate: slack_msg/tg_msg are already fully
    composed (tg_msg's dynamic values already HTML-escaped via _esc_html()
    above) — notify() must pass them through unchanged, not re-escape them
    (see _esc_html's docstring and notification_service._RAW_TEMPLATES).

    Severity routing is preserved exactly: Slack always fires; Telegram
    fires only when `severity` is literally "ALERT" or "CRITICAL" (a
    "HIGH" service-health alert does NOT get Telegram — that was already
    true of the pre-cutover code: the caller's `tg if crit in
    ("CRITICAL", "HIGH") else None` ternary was live but the check here
    excluded "HIGH" regardless of tg_msg, so Telegram never fired for it).
    """
    ok = _notify(slack_msg, severity=_SEVERITY_MAP.get(severity, Severity.WARNING),
                 template="raw", transport=Transport.SLACK).ok
    if severity in ("ALERT", "CRITICAL") and (tg_msg or slack_msg):
        _notify(tg_msg or slack_msg, severity=_SEVERITY_MAP.get(severity, Severity.WARNING),
                template="raw", transport=Transport.TELEGRAM)
    return ok


# ---------------------------------------------------------------------------
# Supabase helper
# ---------------------------------------------------------------------------

def _supabase():
    try:
        sys.path.insert(0, str(REPO_ROOT))
        for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
            if not os.environ.get(k):
                val = _env(k)
                if val:
                    os.environ[k] = val
        from tools.supabase.supabase_client import SupabaseClient
        return SupabaseClient()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Rule 1: Executor stuck at engineering_running
# ---------------------------------------------------------------------------

def _rule_executor_stuck(conn: sqlite3.Connection, client) -> None:
    if client is None:
        return
    try:
        rows = client.select(
            "build_request_inbox",
            columns="request_id,status,created_at",
            limit=100,
        ) or []
    except Exception as exc:
        log.error("[bus:stuck] Supabase query failed: %s", exc)
        return

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_STUCK_MIN)
    stuck = []
    for r in rows:
        if r.get("status") != "engineering_running":
            continue
        try:
            ts = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if ts < cutoff:
            age_min = int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
            stuck.append((r["request_id"], age_min))

    # Resolve stale stuck-alerts for requests that have since moved on
    active_stuck_keys = {f"executor_stuck:{rid}" for rid, _ in stuck}
    for row in conn.execute(
        "SELECT event_key FROM bus_events WHERE event_key LIKE 'executor_stuck:%' AND resolved_at IS NULL"
    ).fetchall():
        if row["event_key"] not in active_stuck_keys:
            _resolve_if_gone(conn, row["event_key"])

    for req_id, age_min in stuck:
        key = f"executor_stuck:{req_id}"
        ev = _upsert_event(conn, key)
        if ev["resolved_at"]:
            _reopen_event(conn, key)
            ev = conn.execute("SELECT * FROM bus_events WHERE event_key=?", (key,)).fetchone()
        if _should_notify(ev, _NOTIFY_COOLDOWN_H):
            msg = (
                f":warning: *Build Executor Stuck* [{age_min}m]\n"
                f"Request `{req_id}` has been at `engineering_running` for {age_min} minutes.\n"
                "The executor may have died mid-run. Manual intervention required:\n"
                "• Reset the row status to `approved` to re-queue, OR\n"
                "• Archive the request if it should not be retried."
            )
            tg = (
                f"⚠️ <b>Build Executor Stuck</b> [{age_min}m]\n"
                f"<code>{_esc_html(req_id)}</code> stuck at <code>engineering_running</code> for {age_min}m.\n"
                "Reset to <code>approved</code> to re-queue or archive if stale."
            )
            if _route("ALERT", msg, tg):
                _mark_notified(conn, key)
                log.info("[bus:stuck] Alerted on stuck request: %s (%dm)", req_id, age_min)


# ---------------------------------------------------------------------------
# Rule 2: Service health
# ---------------------------------------------------------------------------

def _systemd_state(service: str) -> str:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip()  # "active", "inactive", "failed", "activating", etc.
    except Exception:
        return "unknown"


def _backend_healthy() -> bool:
    try:
        with urllib.request.urlopen(_BACKEND_HEALTH_URL, timeout=5) as r:
            data = json.load(r)
            return data.get("status") == "operational"
    except Exception:
        return False


def _emit_service_state_event(event_type: str, svc: str, state: str, crit: str) -> None:
    """MSN-0330 Signal Expansion: mirrors a genuine service-state
    TRANSITION into core_events — never a routine per-cycle poll, only
    the moment something actually changed. Non-blocking, matches every
    other publish_event() caller's own contract."""
    try:
        from core.platform.event_bus import publish_event
        publish_event(
            event_type, domain="platform-operations", source="command_bus",
            recommended_action=f"{svc}: {state}",
            metrics={"service": svc, "state": state, "criticality": crit},
        )
    except Exception:
        pass


def _rule_service_health(conn: sqlite3.Connection) -> None:
    problems: list[tuple[str, str, str]] = []  # (service, state, criticality)

    for svc, crit in _SERVICES.items():
        state = _systemd_state(svc)
        key = f"service_down:{svc}"
        if state == "active":
            if _resolve_if_gone(conn, key):
                _emit_service_state_event("platform.service_recovered", svc, state, crit)
        else:
            problems.append((svc, state, crit))

    # HTTP backend check (only if the service appears active)
    backend_svc_state = _systemd_state("starfleet-backend.service")
    if backend_svc_state == "active" and not _backend_healthy():
        problems.append(("starfleet-backend.service (HTTP)", "unhealthy", "CRITICAL"))

    # Resolve services that came back
    active_keys = {f"service_down:{s}" for s, _, _ in problems}
    for row in conn.execute(
        "SELECT event_key FROM bus_events WHERE event_key LIKE 'service_down:%' AND resolved_at IS NULL"
    ).fetchall():
        if row["event_key"] not in active_keys:
            _resolve_if_gone(conn, row["event_key"])
            log.info("[bus:health] Resolved: %s", row["event_key"])

    for svc, state, crit in problems:
        key = f"service_down:{svc}"
        existing = conn.execute("SELECT 1 FROM bus_events WHERE event_key=?", (key,)).fetchone()
        ev = _upsert_event(conn, key)
        was_resolved = bool(ev["resolved_at"])
        if was_resolved:
            _reopen_event(conn, key)
            ev = conn.execute("SELECT * FROM bus_events WHERE event_key=?", (key,)).fetchone()
        # MSN-0330: emit exactly on a real down-transition — either this
        # service was never down before (existing is None, brand new
        # bus_events row) or it had recovered and is now down again
        # (was_resolved). A service still consecutively down across
        # polling cycles does neither and correctly emits nothing.
        if existing is None or was_resolved:
            _emit_service_state_event("platform.service_down", svc, state, crit)
        if not _should_notify(ev, _NOTIFY_COOLDOWN_H):
            continue

        sev_emoji = {"CRITICAL": ":sos:", "HIGH": ":rotating_light:", "MEDIUM": ":warning:"}.get(crit, ":bell:")
        msg = (
            f"{sev_emoji} *Service Health Alert* [{crit}]\n"
            f"`{svc}` is *{state}*.\n"
            "Check: `systemctl status <service>` | `journalctl -u <service> -n 50`"
        )
        tg = f"🆘 <b>Service Down</b> [{crit}]\n<code>{_esc_html(svc)}</code> is <b>{_esc_html(state)}</b>."
        if _route(crit, msg, tg if crit in ("CRITICAL", "HIGH") else None):
            _mark_notified(conn, key)
            log.info("[bus:health] Alerted: %s is %s [%s]", svc, state, crit)


# ---------------------------------------------------------------------------
# Rule 4: New Idea-status missions
# ---------------------------------------------------------------------------

def _rule_new_missions(conn: sqlite3.Connection, client) -> None:
    if client is None:
        return
    try:
        rows = client.select(
            "missions",
            columns="mission_id,title,status",
            limit=200,
        ) or []
    except Exception as exc:
        log.error("[bus:missions] Supabase query failed: %s", exc)
        return

    ideas = [r for r in rows if (r.get("status") or "").lower() == "idea"]
    for m in ideas:
        mid = m.get("mission_id") or "?"
        title = (m.get("title") or mid)[:70]
        if conn.execute("SELECT 1 FROM seen_missions WHERE mission_id=?", (mid,)).fetchone():
            continue
        # First time seeing this Idea
        conn.execute(
            "INSERT OR IGNORE INTO seen_missions (mission_id, first_seen) VALUES (?, ?)",
            (mid, _now_iso()),
        )
        conn.commit()
        msg = (
            f":bulb: *New Mission — Triage Required*\n"
            f"`{mid}` — {title}\n"
            "Status: *Idea* — awaiting review, approval, or archival.\n"
            "Use `/mission-status` to advance or `/mission-close` to archive."
        )
        _slack(msg)
        log.info("[bus:missions] New Idea mission alerted: %s", mid)


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------

def run_once() -> None:
    """Run one full cycle of all routing rules."""
    log.info("[bus] Running cycle")
    client = _supabase()
    if client is None:
        log.warning("[bus] Supabase unavailable — rules requiring DB will be skipped")

    with _db() as conn:
        _rule_executor_stuck(conn, client)
        _rule_service_health(conn)
        _rule_new_missions(conn, client)

    log.info("[bus] Cycle complete")


def run_loop() -> None:
    """Continuous polling loop. Runs indefinitely; use systemd for lifecycle."""
    import time
    log.info("[bus] Starting command bus (interval=%ds)", _INTERVAL)
    log.info("[bus] Slack channel: %s | Telegram chat: %s",
             _SLACK_CHANNEL or "(not configured)",
             _TG_CHAT_ID or "(not configured)")
    while True:
        try:
            run_once()
        except Exception as exc:
            log.error("[bus] Cycle error (continuing): %s", exc)
        time.sleep(_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [command-bus] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "once":
        run_once()
    else:
        run_loop()
