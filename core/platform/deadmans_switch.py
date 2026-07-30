#!/usr/bin/env python3
"""External dead-man's switch (STARSHIP-REDESIGN.md §4.2 - "the watcher's
watcher").

Closes the "who watches the heartbeat monitor" hole: if
core/platform/verification_engine.py itself goes silent, nothing inside the
platform can be trusted to notice, because the thing that would normally
notice is the thing that's broken. This script is therefore deliberately
NOT part of the verification engine's own process or scheduler - it is a
separate systemd timer (deploy/deadmans-switch.timer), reads Supabase
directly (bypassing the command-centre backend entirely, so an app-tier
outage doesn't mask a verification-engine outage), and sends Telegram
directly via raw HTTP (no bot process, no shared library with the rest of
the platform) - the same minimal-dependency idiom already used by
core/coordination/command_bus.py's _telegram() and
core/platform/notification_service.py's _send_telegram(), copied here
rather than imported, so this script has the fewest possible failure modes
in common with whatever it might be alerting about.

Debounced via a small local state file (outputs/deadmans_switch_state.json)
so a prolonged outage sends one alert per cooldown window, not one per run.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATE_FILE = _REPO_ROOT / "outputs" / "deadmans_switch_state.json"
_COOLDOWN_MINUTES = int(os.environ.get("DEADMANS_SWITCH_ALERT_COOLDOWN_MINUTES", "60"))


def _load_dotenv() -> None:
    env_path = _REPO_ROOT / ".env"
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

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _supabase_get(path: str, timeout: int = 10) -> List[Dict[str, Any]]:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise RuntimeError("Supabase credentials not configured")
    url = f"{_SUPABASE_URL.rstrip('/')}/rest/v1/{path}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": _SUPABASE_KEY,
            "Authorization": f"Bearer {_SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        parsed = json.loads(resp.read().decode("utf-8"))
    return parsed if isinstance(parsed, list) else [parsed]


def _send_telegram(text: str) -> tuple[bool, Optional[str]]:
    """Copy of core/platform/notification_service.py's _send_telegram(),
    deliberately duplicated rather than imported - see module docstring."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    raw_ids = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    chat_id = raw_ids.split(",")[0].strip() if raw_ids else os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False, "missing TELEGRAM_BOT_TOKEN or chat id"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _read_state() -> Dict[str, Any]:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(state: Dict[str, Any]) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass  # best-effort - a failed debounce write must not crash the switch


def check() -> Dict[str, Any]:
    """Returns a report dict. Never raises - a switch that crashes silently
    defeats its own purpose, so every failure path is an explicit 'blind'
    verdict with a reason, not an exception."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    try:
        registry = _supabase_get(
            "domain_registry?domain_key=eq.verification_engine"
            "&select=expected_cadence_minutes,grace_period_minutes"
        )
        state_rows = _supabase_get(
            "verification_state?select=computed_at&order=computed_at.desc&limit=1"
        )
    except Exception as exc:
        return {"blind": True, "reason": f"could not read Supabase: {exc}", "alerted": False}

    reg = registry[0] if registry else {"expected_cadence_minutes": 5, "grace_period_minutes": 15}
    max_age_seconds = (reg["expected_cadence_minutes"] + reg["grace_period_minutes"]) * 60

    if not state_rows:
        blind, reason = True, "verification_state has never been written"
    else:
        computed_at = datetime.fromisoformat(state_rows[0]["computed_at"].replace("Z", "+00:00"))
        age_seconds = (now - computed_at).total_seconds()
        if age_seconds > max_age_seconds:
            blind, reason = True, f"last verification pass was {int(age_seconds / 60)} min ago"
        else:
            blind, reason = False, None

    debounce_state = _read_state()
    alerted = False

    if blind:
        last_alert = debounce_state.get("last_alert_sent_at")
        cooldown_elapsed = True
        if last_alert:
            last_alert_dt = datetime.fromisoformat(last_alert)
            cooldown_elapsed = (now - last_alert_dt).total_seconds() > (_COOLDOWN_MINUTES * 60)
        if cooldown_elapsed:
            ok, err = _send_telegram(
                "I can't verify anything right now. "
                f"{reason}. Treat silence as unknown, not as calm."
            )
            alerted = ok
            if ok:
                debounce_state["last_alert_sent_at"] = now.isoformat()
                _write_state(debounce_state)
    else:
        # Recovered - clear the debounce so the next outage alerts immediately.
        if debounce_state.get("last_alert_sent_at"):
            _write_state({})

    return {"blind": blind, "reason": reason, "alerted": alerted}


if __name__ == "__main__":
    report = check()
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if report.get("blind") else 0)
