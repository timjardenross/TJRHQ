"""Command Operations Bus — cross-service routing and health orchestration.

Polls Supabase and systemd state on a configurable cycle, detects problems,
self-heals where safe, and routes alerts to the Captain across Slack and
Telegram.  This is the thin coordination layer that was previously missing —
it does not replace individual service polling, it coordinates across them.

Routing rules (applied every COMMAND_BUS_INTERVAL seconds, default 300):
  1. executor_stuck       — build_request_inbox row stuck at engineering_running
                            > EXECUTOR_STUCK_MIN minutes → ALERT
  2. service_health       — critical services down or HTTP backend unhealthy → ALERT
  3. executor_needs_restart — executor inactive + approved rows in queue → restart + ALERT
  4. new_missions         — newly created Idea-status missions → one-time triage nudge

Self-healing:
  Executor restart: at most once per EXECUTOR_RESTART_COOLDOWN_MIN (default 30)
  Restart log: outputs/command_bus_restarts.log

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

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS_DIR = REPO_ROOT / "outputs"

# ---------------------------------------------------------------------------
# Config (env vars, with .env fallback)
# ---------------------------------------------------------------------------

def _env(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if v:
        return v
    for envf in (REPO_ROOT / ".env",
                 REPO_ROOT / "platform-runtime" / ".env",
                 REPO_ROOT / "telegram-bot" / ".env",
                 REPO_ROOT / "xo-bot" / ".env"):
        try:
            for line in envf.read_text(encoding="utf-8").splitlines():
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return default


_INTERVAL           = int(_env("COMMAND_BUS_INTERVAL", "300"))       # seconds between cycles
_STUCK_MIN          = int(_env("EXECUTOR_STUCK_MIN", "60"))           # minutes before stuck alert
_RESTART_COOLDOWN   = int(_env("EXECUTOR_RESTART_COOLDOWN_MIN", "30"))# minutes between restarts
_NOTIFY_COOLDOWN_H  = int(_env("COMMAND_BUS_NOTIFY_COOLDOWN_H", "4")) # hours between repeat alerts

_SLACK_TOKEN        = _env("SLACK_BOT_TOKEN")
_SLACK_CHANNEL      = _env("BRIEF_CHANNEL") or _env("BRIEF_USER_ID") or _env("CAPTAINS_INBOX_CHANNEL_ID")
_TG_TOKEN           = _env("TELEGRAM_BOT_TOKEN")
_TG_CHAT_ID         = (_env("TELEGRAM_ALLOWED_CHAT_IDS") or "").split(",")[0].strip()

_BACKEND_HEALTH_URL = _env("BACKEND_HEALTH_URL", "http://localhost:5000/health")

# Services and their criticality (only services we care about monitoring).
# The build executor is intentionally excluded here — it's managed by
# _rule_executor_needs_restart which only alerts when there is pending work.
_SERVICES = {
    "starfleet-slack-bot.service":      "CRITICAL",
    "starfleet-backend.service":        "CRITICAL",
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
_RESTART_LOG = OUTPUTS_DIR / "command_bus_restarts.log"


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


def _should_act(row: sqlite3.Row, cooldown_min: int) -> bool:
    if not row["last_action"]:
        return True
    last = datetime.fromisoformat(row["last_action"])
    return (datetime.now(timezone.utc) - last) >= timedelta(minutes=cooldown_min)


def _mark_acted(conn: sqlite3.Connection, key: str) -> None:
    conn.execute(
        "UPDATE bus_events SET last_action=?, action_count=action_count+1 WHERE event_key=?",
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


def _telegram(message: str) -> bool:
    if not _TG_TOKEN or not _TG_CHAT_ID:
        log.debug("[bus:telegram] No Telegram token/chat_id configured — skipping")
        return False
    payload = json.dumps({"chat_id": _TG_CHAT_ID, "text": message,
                           "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.load(r)
            if not resp.get("ok"):
                log.warning("[bus:telegram] API error: %s", resp.get("description"))
                return False
        return True
    except Exception as exc:
        log.error("[bus:telegram] Request failed: %s", exc)
        return False


def _route(severity: str, slack_msg: str, tg_msg: str | None = None) -> bool:
    """Post to Slack (always) and Telegram (ALERT/CRITICAL). Returns True if Slack succeeded."""
    ok = _slack(slack_msg)
    if severity in ("ALERT", "CRITICAL") and (tg_msg or slack_msg):
        _telegram(tg_msg or slack_msg)
    return ok


def _restart_executor() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["systemctl", "restart", "telegram-build-executor.service"],
            capture_output=True, text=True, timeout=15,
        )
        success = result.returncode == 0
        detail = (result.stderr or result.stdout or "").strip() or "ok"
        entry = f"{_now_iso()} restart={'ok' if success else 'FAILED'} rc={result.returncode} {detail}\n"
        with open(_RESTART_LOG, "a") as f:
            f.write(entry)
        return success, detail
    except Exception as exc:
        return False, str(exc)


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
                f"⚠️ *Build Executor Stuck* [{age_min}m]\n"
                f"`{req_id}` stuck at `engineering_running` for {age_min}m.\n"
                "Reset to `approved` to re-queue or archive if stale."
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
        tg = f"🆘 *Service Down* [{crit}]\n`{svc}` is *{state}*."
        if _route(crit, msg, tg if crit in ("CRITICAL", "HIGH") else None):
            _mark_notified(conn, key)
            log.info("[bus:health] Alerted: %s is %s [%s]", svc, state, crit)


# ---------------------------------------------------------------------------
# Rule 3: Executor needs restart (approved rows queued, executor not running)
# ---------------------------------------------------------------------------

def _rule_executor_needs_restart(conn: sqlite3.Connection, client) -> None:
    if client is None:
        return

    executor_state = _systemd_state("telegram-build-executor.service")
    if executor_state == "active":
        _resolve_if_gone(conn, "executor_needs_restart")
        return

    try:
        rows = client.select(
            "build_request_inbox",
            columns="request_id,status",
            limit=100,
        ) or []
    except Exception as exc:
        log.error("[bus:restart] Supabase query failed: %s", exc)
        return

    approved_pending = [r["request_id"] for r in rows if r.get("status") == "approved"]
    if not approved_pending:
        _resolve_if_gone(conn, "executor_needs_restart")
        return

    key = "executor_needs_restart"
    ev = _upsert_event(conn, key)
    if ev["resolved_at"]:
        _reopen_event(conn, key)
        ev = conn.execute("SELECT * FROM bus_events WHERE event_key=?", (key,)).fetchone()

    action_note = ""
    if _should_act(ev, _RESTART_COOLDOWN):
        ok, detail = _restart_executor()
        _mark_acted(conn, key)
        action_note = f"\n• Auto-restart attempted: {'succeeded' if ok else f'FAILED — {detail}'}"
        log.info("[bus:restart] Executor restart %s: %s", "ok" if ok else "FAILED", detail)
    else:
        action_note = "\n• Restart already attempted recently — manual check may be needed."

    if _should_notify(ev, _NOTIFY_COOLDOWN_H):
        count = len(approved_pending)
        msg = (
            f":construction: *Build Executor Down — Work Queued*\n"
            f"`telegram-build-executor.service` is {executor_state} with "
            f"*{count} approved request(s)* waiting to be processed.{action_note}\n"
            f"Requests: {', '.join(approved_pending[:5])}"
            + (f" (+{count - 5} more)" if count > 5 else "")
        )
        tg = (
            f"🚧 *Executor Down — {count} request(s) queued*{action_note}"
        )
        if _route("ALERT", msg, tg):
            _mark_notified(conn, key)
            log.info("[bus:restart] Alerted on executor down with %d approved requests", count)


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
        _rule_executor_needs_restart(conn, client)
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
