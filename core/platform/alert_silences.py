"""Alert Silences — Alertmanager-style temporary suppression (migration 0205).

The gap this closes: nothing on this platform lets the Captain say "I know
about this, stop notifying me about it for the next N hours" without either
disabling a whole source (`alert_sources.active`, migration 0174 — an
on/off switch, not a timer) or silently ignoring the notification each time
it arrives. Prometheus Alertmanager's actual distinguishing feature over a
plain alerting pipeline is exactly this: a scoped, time-bounded silence
with a reason, not a permanent mute.

This is deliberately NOT a rewrite of any alerting/dedup logic already
working in production — `intelligence/emergency_alert_summary.py`'s hourly
fingerprint+digest logic and `core/coordination/command_bus.py`'s
per-event-key cooldown (`_should_notify`) both already solve "don't repeat
the same notification" for their own callers and are left untouched. A
silence answers a different question — "suppress notifications matching
THIS pattern for THIS window, regardless of whether it's a repeat or a
brand-new alert" — the concrete first use: a planned hazard-reduction burn
(`alerts.alert_type='hazard_reduction'`) in a known jurisdiction generates
expected, non-actionable Emergency Alert Hub alerts; a silence lets the
Captain mute just that jurisdiction+alert_type combination for the burn's
known duration instead of missing a genuinely new emergency_warning
elsewhere, or wading through Advice-tier noise, for hours.

Matching is a plain "every set field must match exactly" AND — no globs,
no regex, no jsonb query language — mirroring `alerts`' own flat column
shape (migration 0174) rather than inventing a new matcher DSL for a
single-user platform with no other consumer yet. A silence with every
match_* field null matches every alert; `create_silence()` does not
special-case or block that (a deliberate "mute everything for an hour"
silence is a legitimate maintenance-window use), but it's on the caller
building the UI/CLI for this to make that scope obvious to a human before
they create one.

Like `core/capture/dedup.py`'s `build_recent_index`/`find_duplicate` split,
the network fetch (`list_active_silences`) and the pure matching logic
(`_matches`/`check_silence`) are separate — a caller processing a batch of
alerts fetches the active-silence set once and passes it to `check_silence`
per alert, rather than one Supabase round-trip per alert.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heartbeat import _KEY, _URL, supabase_get

log = logging.getLogger("alert-silences")

_MATCH_FIELDS = ("jurisdiction", "alert_type", "severity", "source_key")


@dataclass
class Silence:
    id: str
    reason: str
    starts_at: str
    ends_at: str
    jurisdiction: str | None = None
    alert_type: str | None = None
    severity: str | None = None
    source_key: str | None = None


def _matches(silence: dict[str, Any], alert: dict[str, Any]) -> bool:
    """True if every non-null match_* field on `silence` equals the
    corresponding field on `alert`. A silence with all match_* fields null
    matches any alert. Pure — no I/O, directly unit-testable."""
    for field in _MATCH_FIELDS:
        want = silence.get(f"match_{field}")
        if want is not None and alert.get(field) != want:
            return False
    return True


def list_active_silences(at: datetime | None = None) -> list[dict[str, Any]]:
    """Fetches silences currently in effect (starts_at <= at <= ends_at).
    Raises RuntimeError on a Supabase failure — same "let the caller decide
    how to degrade" contract as heartbeat.supabase_get itself; callers on
    a best-effort notification path (see emergency_alerts.py's usage)
    should wrap this in their own try/except rather than have it swallow
    errors silently here."""
    now = (at or datetime.now(timezone.utc)).isoformat()
    return supabase_get(
        f"alert_silences?starts_at=lte.{now}&ends_at=gte.{now}"
        "&select=id,reason,starts_at,ends_at,match_jurisdiction,match_alert_type,match_severity,match_source_key"
    )


def check_silence(
    alert: dict[str, Any],
    active_silences: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Returns the first active silence matching `alert`, or None. Pass a
    pre-fetched `active_silences` list (from list_active_silences(), called
    once per batch) to avoid one Supabase round-trip per alert; omitting it
    fetches fresh — convenient for a one-off check, not for a batch loop."""
    if active_silences is None:
        active_silences = list_active_silences()
    for silence in active_silences:
        if _matches(silence, alert):
            return silence
    return None


def create_silence(
    *,
    reason: str,
    ends_at: str,
    starts_at: str | None = None,
    jurisdiction: str | None = None,
    alert_type: str | None = None,
    severity: str | None = None,
    source_key: str | None = None,
) -> dict[str, Any]:
    """Creates a silence. `reason` is required (an unlabelled silence is
    exactly the kind of thing that's inexplicable a week later on a
    single-user platform with no one else to ask). `ends_at`/`starts_at`
    are ISO 8601 strings; `starts_at` defaults to now. Raises ValueError on
    an empty reason or ends_at <= starts_at, RuntimeError on a Supabase
    failure — this is an explicit Captain action, not a best-effort
    background write, so both fail loudly rather than degrading quietly."""
    if not reason or not reason.strip():
        raise ValueError("reason must not be empty")
    starts = starts_at or datetime.now(timezone.utc).isoformat()
    if ends_at <= starts:
        raise ValueError(f"ends_at ({ends_at}) must be after starts_at ({starts})")

    if not _URL or not _KEY:
        raise RuntimeError("Supabase credentials not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)")

    body = {
        "reason": reason.strip(),
        "starts_at": starts,
        "ends_at": ends_at,
        "match_jurisdiction": jurisdiction,
        "match_alert_type": alert_type,
        "match_severity": severity,
        "match_source_key": source_key,
    }
    req = urllib.request.Request(
        f"{_URL.rstrip('/')}/rest/v1/alert_silences",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "apikey": _KEY,
            "Authorization": f"Bearer {_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 - url built from SUPABASE_URL env var (_URL), always https - matches emergency_alerts.py's _supabase_request
        created = json.loads(resp.read())
    return created[0] if isinstance(created, list) else created


__all__ = [
    "Silence",
    "check_silence",
    "create_silence",
    "list_active_silences",
]
