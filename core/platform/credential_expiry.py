"""Credential expiry monitoring (2026-11-25).

Warns at 30, 14, 7 and 1 day before a registered credential expires, and when it has expired,
through the platform notification service. The registry holds only NON-SECRET metadata
(name, expiry timestamp, a renewal hint): never a credential value.

Registry (JSON list), default /var/lib/credential-expiry/registry.json:
    [{"name": "infisical-machine-identity", "expires_at": "2027-02-22T23:57:00Z",
      "renewal_hint": "short non-secret instruction"}]

Each (name, expires_at) pair alerts once per threshold; a renewed credential gets a new
expires_at and so starts a fresh series. A missing or unreadable registry is itself alerted
(once a day), so the monitor cannot fail silently.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from core.platform.notification_service import Severity, notify

log = logging.getLogger(__name__)

THRESHOLD_DAYS = (30, 14, 7, 1)
REGISTRY_PATH = Path(os.environ.get("CREDENTIAL_EXPIRY_REGISTRY", "/var/lib/credential-expiry/registry.json"))
STATE_PATH = Path(os.environ.get("CREDENTIAL_EXPIRY_STATE", "/var/lib/credential-expiry/state.json"))


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def _save_state(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    os.replace(tmp, path)


def due_alerts(entries: list[dict], state: dict, now: datetime) -> list[dict]:
    """Pure function: which alerts are due now, given prior state. Mutates state."""
    out = []
    for e in entries:
        name, exp = e["name"], _parse(e["expires_at"])
        key = f"{name}|{exp.isoformat()}"
        days = (exp - now).total_seconds() / 86400
        if days <= 0:
            today = now.date().isoformat()
            if state.get(key) != f"expired:{today}":
                state[key] = f"expired:{today}"
                out.append({"name": name, "days": days, "level": "expired", "hint": e.get("renewal_hint", ""), "expires": exp})
            continue
        t = next((t for t in sorted(THRESHOLD_DAYS) if days <= t), None)
        if t is None:
            continue
        prev = state.get(key)
        if isinstance(prev, int) and prev <= t:
            continue
        state[key] = t
        out.append({"name": name, "days": days, "level": t, "hint": e.get("renewal_hint", ""), "expires": exp})
    return out


def _render(a: dict) -> tuple[str, str, str]:
    if a["level"] == "expired":
        return (f"Credential EXPIRED: {a['name']}", Severity.CRITICAL.value,
                f"{a['name']} expired {a['expires']:%Y-%m-%d %H:%M} UTC. Renew now. {a['hint']}")
    sev = Severity.WARNING if a["level"] >= 14 else Severity.ALERT if a["level"] > 1 else Severity.CRITICAL
    return (f"Credential expires in {int(a['days'])} day(s): {a['name']}", sev.value,
            f"{a['name']} expires {a['expires']:%Y-%m-%d %H:%M} UTC (threshold: {a['level']} day). {a['hint']}")


def run_check(now: datetime | None = None, notify_fn: Callable | None = None,
              registry: Path | None = None, state_path: Path | None = None) -> list[dict]:
    """Run once. Returns the alerts that were due. Never raises into the scheduler."""
    now = now or datetime.now(timezone.utc)
    registry, state_path = registry or REGISTRY_PATH, state_path or STATE_PATH
    if notify_fn is None:
        def notify_fn(title, severity, body):
            notify(body, title=title, severity=Severity(severity), template="alert")
    try:
        state = _load_json(state_path, {})
        try:
            entries = _load_json(registry, None)
            if not isinstance(entries, list) or not entries:
                raise ValueError("registry missing, empty or not a list")
            for e in entries:
                _parse(e["expires_at"])
                e["name"]
        except Exception as exc:  # noqa: BLE001 - a broken registry must alert, not crash the shared scheduler
            key, today = "registry-error", now.date().isoformat()
            if state.get(key) != today:
                state[key] = today
                _save_state(state, state_path)
                notify_fn("Credential expiry registry unreadable", "alert", f"{registry}: {exc}")
            log.error("credential expiry registry problem: %s", exc)
            return []
        state.pop("registry-error", None)
        alerts = due_alerts(entries, state, now)
        for a in alerts:
            title, sev, body = _render(a)
            notify_fn(title, sev, body)
            log.warning("credential expiry alert: %s", title)
        _save_state(state, state_path)
        log.info("credential expiry check: %d entries, %d alerts", len(entries), len(alerts))
        return alerts
    except Exception as exc:  # noqa: BLE001 - scheduled-job boundary, already logged
        log.error("credential expiry check failed: %s", exc)
        return []


def set_entry(name: str, expires_at: str, hint: str | None = None, registry: Path | None = None) -> None:
    """Create or update one registry entry (used after every rotation so the monitor tracks the new expiry)."""
    registry = registry or REGISTRY_PATH
    _parse(expires_at)  # validate
    entries = _load_json(registry, [])
    entries = [e for e in entries if e.get("name") != name]
    old = next((e for e in _load_json(registry, []) if e.get("name") == name), {})
    entries.append({"name": name, "expires_at": expires_at, "renewal_hint": hint or old.get("renewal_hint", "")})
    registry.parent.mkdir(parents=True, exist_ok=True)
    tmp = registry.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=1))
    os.replace(tmp, registry)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Credential expiry registry (non-secret metadata only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("set", help="record a new expiry after a rotation")
    s.add_argument("name")
    s.add_argument("expires_at", help="ISO 8601, e.g. 2027-02-22T23:57:00Z")
    s.add_argument("--hint")
    sub.add_parser("check", help="run the check now")
    a = ap.parse_args(argv)
    if a.cmd == "set":
        set_entry(a.name, a.expires_at, a.hint)
        print(f"recorded {a.name} expires {a.expires_at}")
    elif a.cmd == "list":
        for e in _load_json(REGISTRY_PATH, []):
            print(f"{e['name']}  {e['expires_at']}")
    else:
        print(run_check())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
