#!/usr/bin/env python3
"""Command Operations Bus — cross-service routing and health orchestration.

Polls Supabase and systemd state on a configurable cycle, detects problems,
self-heals where safe, and routes alerts to the Captain via Telegram.  This
is the thin coordination layer that was previously missing — it does not
replace individual service polling, it coordinates across them.

Routing rules (applied every COMMAND_BUS_INTERVAL seconds, default 300):
  1. executor_stuck       — build_request_inbox row stuck at engineering_running
                            > EXECUTOR_STUCK_MIN minutes → ALERT
  2. service_health       — critical services down or HTTP backend unhealthy → ALERT
  3. new_missions         — newly created Idea-status missions → one-time triage nudge
  4. number_one_escalations — CRITICAL/HIGH escalations from Number One's brief
                            (core/coordination/number_one.py, via context_service.py's
                            _http_number_one_brief()) → ALERT/CRITICAL. USS-TJR-MSN-0362
                            candidate A (2026-09-08): Number One catches PR CI failures,
                            blocked P0 missions, etc. that the Captain wouldn't otherwise
                            see until asked. MEDIUM-level escalations and follow-ups are
                            deliberately NOT pushed — visible on Mission Workbench, not
                            paged. Suppressed during quiet hours (7pm-7am Brisbane,
                            NUMBER_ONE_QUIET_HOURS_START/_END) — an escalation still open
                            when quiet hours end fires on the next cycle, never dropped.

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
  Telegram — all alerts, every severity (TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_CHAT_IDS)
             2026-09-08: Slack retired as a transport (Captain direction — Slack was
             disabled). Telegram is now the only channel, so routing no longer gates
             by severity the way it did when Slack carried everything and Telegram
             was ALERT/CRITICAL-only overflow — see _route()'s docstring.

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
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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

# USS-TJR-MSN-0362 candidate A (2026-09-08): quiet hours for Number One's
# escalation push specifically — the Captain's answer was 7pm-7am. Scoped to
# this one rule only, not the other alerts in this file (executor_stuck/
# service_health/new_missions predate this and nobody asked for their
# behaviour to change — a genuine service outage at 2am should still page).
_QUIET_HOURS_START = int(_env("NUMBER_ONE_QUIET_HOURS_START", "19"))  # 24h, Australia/Brisbane
_QUIET_HOURS_END   = int(_env("NUMBER_ONE_QUIET_HOURS_END", "7"))
_NUMBER_ONE_TZ      = ZoneInfo("Australia/Brisbane")                  # matches wellness_officer/intelligence.py's convention

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

def _esc_html(value: object) -> str:
    """Escape a DYNAMIC value for Telegram's HTML parse_mode, before it's
    interpolated into a Telegram-bound message string, which mixes
    intentional <b>/<code> HTML with runtime values.

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


def _route(severity: str, tg_msg: str) -> bool:
    """Post to Telegram. Returns True on success.

    2026-09-08 (Slack retirement, Captain direction — Slack was disabled):
    Telegram is now the only transport. Before this, Slack carried every
    severity and Telegram only fired for ALERT/CRITICAL (a "HIGH"
    service-health alert never reached Telegram at all) — that gating
    existed because Slack was the always-on channel and Telegram was
    overflow for the urgent cases. With Slack gone, gating by severity
    would silently drop MEDIUM/HIGH alerts entirely instead of just
    changing which channel carries them, so every severity now routes to
    Telegram. `tg_msg` must already be fully composed (dynamic values
    already HTML-escaped via _esc_html() above) — notify() with
    template="raw" passes it through unchanged, not re-escaped (see
    _esc_html's docstring and notification_service._RAW_TEMPLATES).
    """
    return _notify(tg_msg, severity=_SEVERITY_MAP.get(severity, Severity.WARNING),
                    template="raw", transport=Transport.TELEGRAM).ok


def _in_number_one_quiet_hours() -> bool:
    """True during the Captain's quiet hours for Number One's escalation
    push (USS-TJR-MSN-0362 candidate A, 7pm-7am Brisbane by default).
    Handles the overnight wrap (start > end) the same way as a same-day
    window would — e.g. 19 <= hour or hour < 7."""
    hour = datetime.now(_NUMBER_ONE_TZ).hour
    if _QUIET_HOURS_START <= _QUIET_HOURS_END:
        return _QUIET_HOURS_START <= hour < _QUIET_HOURS_END
    return hour >= _QUIET_HOURS_START or hour < _QUIET_HOURS_END


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
    except Exception:  # noqa: BLE001 - documented degraded state: None signals 'Supabase unavailable' to every caller of this factory
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
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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
            tg = (
                f"⚠️ <b>Build Executor Stuck</b> [{age_min}m]\n"
                f"<code>{_esc_html(req_id)}</code> stuck at <code>engineering_running</code> for {age_min}m.\n"
                "Reset to <code>approved</code> to re-queue or archive if stale."
            )
            if _route("ALERT", tg):
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
    except Exception:  # noqa: BLE001 - systemctl probe; 'unknown' is a valid status value alongside active/inactive/failed
        return "unknown"


def _backend_healthy() -> bool:
    try:
        with urllib.request.urlopen(_BACKEND_HEALTH_URL, timeout=5) as r:  # nosec B310 - url is BACKEND_HEALTH_URL env var with fixed localhost default, not user input - reviewed 2026-09-12
            data = json.load(r)
            return data.get("status") == "operational"
    except Exception:  # noqa: BLE001 - health-check probe; False is the documented 'not healthy' result for any failure mode
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
    except Exception:  # noqa: BLE001 - best-effort event emission; must not break the health-monitoring loop it's reporting from
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

        tg = f"🆘 <b>Service Down</b> [{crit}]\n<code>{_esc_html(svc)}</code> is <b>{_esc_html(state)}</b>."
        if _route(crit, tg):
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
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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
        tg = (
            f"💡 <b>New Mission — Triage Required</b>\n"
            f"<code>{_esc_html(mid)}</code> — {_esc_html(title)}\n"
            "Status: <b>Idea</b> — awaiting review, approval, or archival via Mission Workbench."
        )
        _route("MEDIUM", tg)
        log.info("[bus:missions] New Idea mission alerted: %s", mid)


# ---------------------------------------------------------------------------
# Rule 5: Number One escalations (USS-TJR-MSN-0362 candidate A, 2026-09-08)
# ---------------------------------------------------------------------------

_NUMBER_ONE_ALERT_EMOJI = {"CRITICAL": "🆘", "HIGH": "🔺"}


def _get_number_one_brief() -> dict | None:
    """Fetch Number One's brief (escalations, follow-ups, etc.) via the same
    function context_service.py's /brief/number-one endpoint calls — no
    reimplemented scoring/escalation logic, this rule only routes what
    NumberOne + pr_health.py already computed. Direct in-process import
    (same convention core/context-assembly/tests/test_number_one_brief.py
    uses), not HTTP: command_bus.py, context_service.py, and number_one.py
    all run in the same deployed environment/venv. Returns None on any
    failure — this rule is best-effort and must never break the rest of
    the polling cycle."""
    try:
        for p in (REPO_ROOT / "core" / "context-assembly", REPO_ROOT / "core" / "coordination", REPO_ROOT):
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
        import context_service
        return context_service._http_number_one_brief()
    except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
        log.warning("[bus:number_one] Could not fetch Number One's brief: %s", exc)
        return None


def _rule_number_one_escalations(conn: sqlite3.Connection) -> None:
    """Push Number One's CRITICAL/HIGH escalations (PR CI failing, blocked
    P0 missions, etc.) to Telegram — the Captain direction behind this:
    'Number One should also drive what lands in my face' (2026-09-08).
    MEDIUM escalations and follow-ups stay visible on Mission Workbench
    only, not pushed — this rule is deliberately narrower than the full
    brief. Suppressed during quiet hours (_in_number_one_quiet_hours());
    an escalation still open once quiet hours end is notified on the next
    cycle — quiet hours delay delivery, they never drop it, since a
    suppressed escalation is simply never marked notified."""
    brief = _get_number_one_brief()
    if brief is None:
        return

    relevant = [
        e for e in (brief.get("escalations") or [])
        if str(e.get("level", "")).upper() in ("CRITICAL", "HIGH")
    ]

    def _key(e: dict) -> str:
        return f"number_one_escalation:{e.get('escalation_type', 'UNKNOWN')}:{e.get('mission_id', '?')}"

    # Resolve escalations that are no longer present (mirrors _rule_service_health).
    active_keys = {_key(e) for e in relevant}
    for row in conn.execute(
        "SELECT event_key FROM bus_events WHERE event_key LIKE 'number_one_escalation:%' AND resolved_at IS NULL"
    ).fetchall():
        if row["event_key"] not in active_keys:
            _resolve_if_gone(conn, row["event_key"])

    quiet = _in_number_one_quiet_hours()
    for e in relevant:
        key = _key(e)
        ev = _upsert_event(conn, key)
        if ev["resolved_at"]:
            _reopen_event(conn, key)
            ev = conn.execute("SELECT * FROM bus_events WHERE event_key=?", (key,)).fetchone()
        if not _should_notify(ev, _NOTIFY_COOLDOWN_H):
            continue
        if quiet:
            # Leave it un-notified — _should_notify() will still be True on
            # the next cycle after quiet hours end, so nothing is dropped.
            continue

        level = str(e.get("level", "")).upper()
        emoji = _NUMBER_ONE_ALERT_EMOJI.get(level, "⚠️")
        mission_id = e.get("mission_id") or "?"
        reason = e.get("reason") or ""
        recommendation = e.get("recommendation") or ""
        tg = (
            f"{emoji} <b>Number One — {_esc_html(e.get('escalation_type', 'ESCALATION'))}</b> [{level}]\n"
            f"<code>{_esc_html(mission_id)}</code> — {_esc_html(reason)}"
        )
        if recommendation:
            tg += f"\n→ {_esc_html(recommendation)}"

        if _route(level, tg):
            _mark_notified(conn, key)
            log.info("[bus:number_one] Alerted: %s on %s [%s]", e.get("escalation_type"), mission_id, level)


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
        _rule_number_one_escalations(conn)

    log.info("[bus] Cycle complete")


def run_loop() -> None:
    """Continuous polling loop. Runs indefinitely; use systemd for lifecycle."""
    import time
    log.info("[bus] Starting command bus (interval=%ds)", _INTERVAL)
    log.info("[bus] Telegram chat: %s", _TG_CHAT_ID or "(not configured)")
    while True:
        try:
            run_once()
        except Exception as exc:  # noqa: BLE001 - already logs the causing exception at this boundary; broad catch is deliberate so one failure mode can't silently escape
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
