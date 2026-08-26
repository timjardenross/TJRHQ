"""Emergency Alert Hub orchestrator (migration 0174).

Runs every registered alert_sources adapter (intelligence/ingestion/
emergency_alert_adapters/), upserts results into `alerts`, expires alerts
no longer present in a source's latest fetch, and records a per-source
heartbeat into domain_heartbeats (core/platform/heartbeat.py) — the same
mechanism every other scheduled job on the platform uses, so these sources
show up on the existing Agent/Job dashboard with no bespoke health UI.

Called from intelligence/scheduler.py. Never lets one source's failure
stop the others — same fail-isolated-per-source contract as
intelligence/scheduler.py's existing source-collection jobs.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))
from heartbeat import _URL, _KEY, record_heartbeat, supabase_get  # noqa: E402

from intelligence.ingestion.emergency_alert_adapters import (
    act_esa, nsw_rfs, nt_securent, qld_fire, sa_cfs, tas_fire, vic_emergency, wa_dfes,
)
from core.notifications.resend_email import send_email

# Captain-directed 2026-08-27, temporary until tjrmindbody.com's Resend
# domain verification is fixed (broken as of this session): Resend's
# sandbox mode only delivers to the account's own signup email, not
# timjardenross@outlook.com — confirmed live. Override via env once the
# domain is verified; no code change needed.
_EMERGENCY_EMAIL_TO = os.environ.get("EMERGENCY_ALERT_EMAIL_TO", "timjardenross1986@gmail.com")

log = logging.getLogger("emergency-alerts")

# source_key -> (adapter module, domain_registry.domain_key from migration 0174)
_ADAPTERS = {
    "nsw_rfs":       (nsw_rfs,       "emergency_alert_nsw_rfs"),
    "vic_emergency": (vic_emergency, "emergency_alert_vic"),
    "qld_fire":      (qld_fire,      "emergency_alert_qld"),
    "sa_cfs":        (sa_cfs,        "emergency_alert_sa"),
    "act_esa":       (act_esa,       "emergency_alert_act"),
    "wa_dfes":       (wa_dfes,       "emergency_alert_wa"),
    "tas_fire":      (tas_fire,      "emergency_alert_tas"),
    "nt_securent":   (nt_securent,   "emergency_alert_nt"),
}


def _supabase_request(method: str, path: str, body: Optional[dict] = None, extra_headers: Optional[dict] = None, timeout: int = 15) -> None:
    if not _URL or not _KEY:
        raise RuntimeError("Supabase credentials not configured")
    url = f"{_URL.rstrip('/')}/rest/v1/{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "apikey": _KEY,
        "Authorization": f"Bearer {_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout):
        return


def _upsert_batch(rows: list[dict]) -> None:
    if not rows:
        return
    _supabase_request(
        "POST",
        "alerts?on_conflict=source_key,event_key",
        body=rows,
        extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
    )


def _expire_stale(source_key: str, run_started_at: str) -> int:
    """Alerts for this source still marked active but not touched by this
    run (last_seen_at older than run_started_at) are gone from the source's
    own current feed — the state-machine rule from the scope doc: "an alert
    becomes inactive when the source clears it". Returns count expired."""
    try:
        existing = supabase_get(
            f"alerts?source_key=eq.{source_key}&is_active=eq.true"
            f"&last_seen_at=lt.{urllib.parse.quote(run_started_at, safe='')}&select=id"
        )
    except Exception as exc:
        log.warning("[emergency-alerts] %s: failed to read stale alerts: %s", source_key, exc)
        return 0
    if not existing:
        return 0
    ids = ",".join(row["id"] for row in existing)
    try:
        _supabase_request(
            "PATCH",
            f"alerts?id=in.({ids})",
            body={"is_active": False, "status": "expired"},
        )
    except Exception as exc:
        log.warning("[emergency-alerts] %s: failed to expire %d stale alert(s): %s", source_key, len(existing), exc)
        return 0
    return len(existing)


def _send_emergency_warning_emails(source_key: str) -> int:
    """Email (Resend, core/notifications/resend_email.py) for every
    currently-active severity='emergency_warning' alert on this source that
    hasn't been emailed yet (alerts.emergency_email_sent_at is null —
    persistent dedupe, migration 0175). Runs after the upsert so it only
    sees this run's real, current state. Never raises — a notification
    failure must never break the ingestion job it's attached to."""
    try:
        rows = supabase_get(
            f"alerts?source_key=eq.{source_key}&severity=eq.emergency_warning"
            "&is_active=eq.true&emergency_email_sent_at=is.null"
            "&select=id,headline,jurisdiction,location,description,canonical_url,issued_at"
        )
    except Exception as exc:
        log.warning("[emergency-alerts] %s: failed to read unnotified emergency warnings: %s", source_key, exc)
        return 0

    sent = 0
    for row in rows:
        subject = f"🚨 EMERGENCY WARNING — {row['jurisdiction']} — {row['headline']}"
        html = (
            f"<p><strong>{row['headline']}</strong></p>"
            f"<p>Jurisdiction: {row['jurisdiction']}<br>"
            f"Location: {row.get('location') or '—'}<br>"
            f"Issued: {row.get('issued_at') or '—'}</p>"
            f"<p>{row.get('description') or ''}</p>"
            + (f"<p><a href=\"{row['canonical_url']}\">Official source</a></p>" if row.get("canonical_url") else "")
        )
        if not send_email(to=_EMERGENCY_EMAIL_TO, subject=subject, html=html):
            log.warning("[emergency-alerts] %s: email send failed for alert %s — will retry next run (dedupe flag not set)", source_key, row["id"])
            continue
        try:
            _supabase_request("PATCH", f"alerts?id=eq.{row['id']}", body={"emergency_email_sent_at": datetime.now(timezone.utc).isoformat()})
            sent += 1
        except Exception as exc:
            log.warning("[emergency-alerts] %s: sent email but failed to mark alert %s notified — may re-send next run: %s", source_key, row["id"], exc)
    return sent


def run_source(source_key: str) -> dict:
    """Run one source's adapter end to end. Never raises — failure is
    captured in the returned dict and recorded as a failed heartbeat, same
    fail-isolated contract as every adapter in intelligence/scheduler.py."""
    adapter, domain_key = _ADAPTERS[source_key]
    run_started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    try:
        alerts = adapter.fetch()
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        record_heartbeat(domain_key, status="failed", error_message=str(exc)[:500], latency_ms=latency_ms)
        log.warning("[emergency-alerts] %s: fetch failed: %s", source_key, exc)
        return {"source_key": source_key, "error": str(exc), "count": 0}

    if not alerts and hasattr(adapter, "NOT_YET_IMPLEMENTED"):
        # Scrape-tier sources (wa_dfes/tas_fire/nt_securent) with no
        # structured extraction yet — 'skipped' is the honest status
        # (domain_heartbeats CHECK constraint, migration 0071), not 'ok'
        # (would falsely claim a clean zero-alerts run) or 'failed'
        # (nothing actually errored).
        record_heartbeat(domain_key, status="skipped", detail=adapter.NOT_YET_IMPLEMENTED)
        return {"source_key": source_key, "count": 0, "skipped": True}

    rows = []
    for a in alerts:
        row = asdict(a)
        closed = row.pop("closed")  # not a DB column — CanonicalAlert-only signal, see base.py
        row["status"] = "expired" if closed else "active"
        row["is_active"] = not closed
        row["last_seen_at"] = run_started_at
        rows.append(row)

    try:
        _upsert_batch(rows)
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        record_heartbeat(domain_key, status="failed", error_message=f"upsert failed: {exc}"[:500], latency_ms=latency_ms)
        log.warning("[emergency-alerts] %s: upsert failed: %s", source_key, exc)
        return {"source_key": source_key, "error": str(exc), "count": len(rows)}

    expired = _expire_stale(source_key, run_started_at)
    emails_sent = _send_emergency_warning_emails(source_key)

    # Surfaced in the heartbeat detail (visible on the workbench's Source
    # Health panel and the Agent/Job dashboard) so a source starting to leak
    # unclassified alerts — like SA CFS's HAYBOROUGH, caught 2026-08-26 by
    # spotting it in the UI — shows up on every run instead of needing a
    # manual audit each time.
    unknown_count = sum(1 for a in alerts if a.severity == "unknown")
    detail = f"{len(rows)} alert(s), {unknown_count} unknown severity, {expired} expired"
    if emails_sent:
        detail += f", {emails_sent} emergency email(s) sent"

    latency_ms = int((time.monotonic() - t0) * 1000)
    record_heartbeat(domain_key, status="ok", detail=detail, latency_ms=latency_ms)
    return {"source_key": source_key, "count": len(rows), "unknown_severity": unknown_count, "expired": expired, "emails_sent": emails_sent}


def run_all() -> dict:
    results = {}
    for source_key in _ADAPTERS:
        results[source_key] = run_source(source_key)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_all(), indent=2, default=str))
