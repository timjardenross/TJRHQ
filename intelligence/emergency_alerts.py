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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))
import alert_silences
from heartbeat import _KEY, _URL, record_heartbeats, supabase_get
from heartbeat import record_heartbeat as _record_heartbeat

from core.notifications.resend_email import send_email
from intelligence.ingestion.emergency_alert_adapters import (
    act_esa,
    bom_warnings,
    nsw_rfs,
    nt_securent,
    qld_fire,
    sa_cfs,
    tas_fire,
    vic_emergency,
    wa_dfes,
)

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
    # BOM state/territory warnings (migration 0176) — flood/severe-weather/
    # cyclone national coverage, complements the fire-agency feeds above.
    "bom_nsw":       (bom_warnings.nsw, "emergency_alert_bom_nsw"),
    "bom_nt":        (bom_warnings.nt,  "emergency_alert_bom_nt"),
    "bom_qld":       (bom_warnings.qld, "emergency_alert_bom_qld"),
    "bom_sa":        (bom_warnings.sa,  "emergency_alert_bom_sa"),
    "bom_tas":       (bom_warnings.tas, "emergency_alert_bom_tas"),
    "bom_vic":       (bom_warnings.vic, "emergency_alert_bom_vic"),
    "bom_wa":        (bom_warnings.wa,  "emergency_alert_bom_wa"),
    "bom_act":       (bom_warnings.act, "emergency_alert_bom_act"),
}


def _supabase_request(method: str, path: str, body: dict | None = None, extra_headers: dict | None = None, timeout: int = 15) -> None:
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
    with urllib.request.urlopen(req, timeout=timeout):  # nosec B310 - url is built from SUPABASE_URL env var (_URL), always https - reviewed 2026-09-12
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
    except Exception as exc:  # noqa: BLE001 - best-effort stale-alerts read, already logged; caller treats 0 as 'nothing expired this run'
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
    except Exception as exc:  # noqa: BLE001 - best-effort expire-stale-alerts write, already logged
        log.warning("[emergency-alerts] %s: failed to expire %d stale alert(s): %s", source_key, len(existing), exc)
        return 0
    return len(existing)


def _expire_stale_many(source_keys: list[str], run_started_at: str) -> dict[str, int]:
    """_expire_stale() for every source run_all() upserted this tick, in one
    read + one PATCH instead of a read (+ PATCH) per source — the per-source
    version was ~1.4k requests/day. All sources in a run_all() share one
    run_started_at, so the "not touched by this run" rule is unchanged.
    Returns expired counts per source_key."""
    if not source_keys:
        return {}
    try:
        existing = supabase_get(
            f"alerts?source_key=in.({','.join(source_keys)})&is_active=eq.true"
            f"&last_seen_at=lt.{urllib.parse.quote(run_started_at, safe='')}&select=id,source_key"
        )
    except Exception as exc:  # noqa: BLE001 - best-effort stale-alerts read, already logged; caller treats {} as 'nothing expired this run'
        log.warning("[emergency-alerts] failed to read stale alerts for %d source(s): %s", len(source_keys), exc)
        return {}
    if not existing:
        return {}
    ids = ",".join(row["id"] for row in existing)
    try:
        _supabase_request(
            "PATCH",
            f"alerts?id=in.({ids})",
            body={"is_active": False, "status": "expired"},
        )
    except Exception as exc:  # noqa: BLE001 - best-effort expire-stale-alerts write, already logged
        log.warning("[emergency-alerts] failed to expire %d stale alert(s): %s", len(existing), exc)
        return {}
    counts: dict[str, int] = {}
    for row in existing:
        counts[row["source_key"]] = counts.get(row["source_key"], 0) + 1
    return counts


def _send_emergency_warning_emails(source_key: str) -> int:
    """Email (Resend, core/notifications/resend_email.py) for every
    currently-active severity='emergency_warning' alert on this source that
    hasn't been emailed yet (alerts.emergency_email_sent_at is null —
    persistent dedupe, migration 0175). Runs after the upsert so it only
    sees this run's real, current state. Never raises — a notification
    failure must never break the ingestion job it's attached to.

    A row matching an active alert_silences rule (migration 0205 — e.g. a
    planned hazard-reduction burn muted for this jurisdiction+alert_type)
    is skipped WITHOUT setting emergency_email_sent_at, so a still-active
    alert is naturally picked up and emailed on the next run once the
    silence expires — no separate "resume" step needed."""
    try:
        rows = supabase_get(
            f"alerts?source_key=eq.{source_key}&severity=eq.emergency_warning"
            "&is_active=eq.true&emergency_email_sent_at=is.null"
            "&select=id,headline,jurisdiction,alert_type,location,description,canonical_url,issued_at"
        )
    except Exception as exc:  # noqa: BLE001 - best-effort unnotified-warnings read, already logged; caller treats 0 as 'nothing to notify'
        log.warning("[emergency-alerts] %s: failed to read unnotified emergency warnings: %s", source_key, exc)
        return 0
    if not rows:
        return 0

    try:
        active_silences = alert_silences.list_active_silences()
    except Exception as exc:  # noqa: BLE001 - a silence-lookup failure must never block a real emergency warning email; degrade to "no active silences"
        log.warning("[emergency-alerts] %s: failed to read active silences (proceeding as if none): %s", source_key, exc)
        active_silences = []

    sent = 0
    for row in rows:
        silenced = alert_silences.check_silence(
            {"jurisdiction": row["jurisdiction"], "alert_type": row.get("alert_type"), "severity": "emergency_warning", "source_key": source_key},
            active_silences,
        )
        if silenced:
            log.info("[emergency-alerts] %s: alert %s silenced (%s) — email suppressed", source_key, row["id"], silenced.get("reason"))
            continue

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
        except Exception as exc:  # noqa: BLE001 - per-alert notification-flag write inside a loop — one bad write must not abort the batch, already logged with the alert id
            log.warning("[emergency-alerts] %s: sent email but failed to mark alert %s notified — may re-send next run: %s", source_key, row["id"], exc)
    return sent


def run_source(source_key: str, run_started_at: str | None = None, heartbeats: list[dict] | None = None) -> dict:
    """Run one source's adapter end to end. Never raises — failure is
    captured in the returned dict and recorded as a failed heartbeat, same
    fail-isolated contract as every adapter in intelligence/scheduler.py.

    Standalone (the defaults) it does everything itself. run_all() passes a
    shared run_started_at and a `heartbeats` list: heartbeats are collected
    for one batched write, and stale-alert expiry is left to run_all()'s
    single _expire_stale_many() pass (the result carries "pending_expiry").
    Emergency-warning emails always stay here, per source, so a warning is
    never held back waiting for later sources to finish."""
    adapter, domain_key = _ADAPTERS[source_key]
    batched = heartbeats is not None
    run_started_at = run_started_at or datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    def record_heartbeat(domain_key, **fields):
        if batched:
            heartbeats.append({"domain_key": domain_key, **fields})
        else:
            _record_heartbeat(domain_key, **fields)

    try:
        alerts = adapter.fetch()
    except Exception as exc:  # noqa: BLE001 - per-source fetch job boundary — already logged + heartbeat-recorded with latency
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
    except Exception as exc:  # noqa: BLE001 - per-source upsert job boundary — already logged + heartbeat-recorded with latency
        latency_ms = int((time.monotonic() - t0) * 1000)
        record_heartbeat(domain_key, status="failed", error_message=f"upsert failed: {exc}"[:500], latency_ms=latency_ms)
        log.warning("[emergency-alerts] %s: upsert failed: %s", source_key, exc)
        return {"source_key": source_key, "error": str(exc), "count": len(rows)}

    expired = 0 if batched else _expire_stale(source_key, run_started_at)
    # Only look for unsent emergency warnings when this run's feed actually
    # carries an active one. Every unsent row the query could return is an
    # active emergency_warning for this source, and a still-active alert is
    # re-upserted on every run — so this still retries failed sends and
    # picks up alerts whose silence has expired, without a GET per source
    # per run (~1.4k/day) when there are none (the overwhelmingly common case).
    has_active_warning = any(r["severity"] == "emergency_warning" and r["is_active"] for r in rows)
    emails_sent = _send_emergency_warning_emails(source_key) if has_active_warning else 0

    # Surfaced in the heartbeat detail (visible on the workbench's Source
    # Health panel and the Agent/Job dashboard) so a source starting to leak
    # unclassified alerts — like SA CFS's HAYBOROUGH, caught 2026-08-26 by
    # spotting it in the UI — shows up on every run instead of needing a
    # manual audit each time.
    unknown_count = sum(1 for a in alerts if a.severity == "unknown")
    latency_ms = int((time.monotonic() - t0) * 1000)
    if batched:
        # run_all() fills in detail once its single expiry pass has the count.
        heartbeats.append({
            "domain_key": domain_key, "status": "ok", "latency_ms": latency_ms,
            "_counts": (len(rows), unknown_count, emails_sent),
        })
    else:
        record_heartbeat(domain_key, status="ok", detail=_ok_detail(len(rows), unknown_count, expired, emails_sent), latency_ms=latency_ms)
    return {
        "source_key": source_key, "count": len(rows), "unknown_severity": unknown_count,
        "expired": expired, "emails_sent": emails_sent, "pending_expiry": batched,
    }


def run_all() -> dict:
    """Every source in one tick, sharing a run_started_at: stale-alert expiry
    runs once across all upserted sources and heartbeats go out in one POST
    (was ~4 requests per source per 15-min tick)."""
    run_started_at = datetime.now(timezone.utc).isoformat()
    heartbeats: list[dict] = []
    results = {}
    for source_key in _ADAPTERS:
        results[source_key] = run_source(source_key, run_started_at=run_started_at, heartbeats=heartbeats)

    pending = [key for key, result in results.items() if result.pop("pending_expiry", False)]
    expired = _expire_stale_many(pending, run_started_at)
    for key in pending:
        results[key]["expired"] = expired.get(key, 0)
    expired_by_domain = {_ADAPTERS[key][1]: expired.get(key, 0) for key in pending}
    for hb in heartbeats:
        counts = hb.pop("_counts", None)
        if counts is not None:
            n_rows, unknown_count, emails_sent = counts
            hb["detail"] = _ok_detail(n_rows, unknown_count, expired_by_domain.get(hb["domain_key"], 0), emails_sent)

    record_heartbeats(heartbeats)
    return results


def _ok_detail(n_rows: int, unknown_count: int, expired: int, emails_sent: int) -> str:
    detail = f"{n_rows} alert(s), {unknown_count} unknown severity, {expired} expired"
    if emails_sent:
        detail += f", {emails_sent} emergency email(s) sent"
    return detail


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_all(), indent=2, default=str))
