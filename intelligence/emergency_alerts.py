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

import html
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))
import alert_silences
import bom_attention
import site_matching
from heartbeat import _KEY, _URL, record_heartbeats, supabase_get
from heartbeat import record_heartbeat as _record_heartbeat

from core.notifications import resend_email as _resend_email
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


# A source whose fetch SUCCEEDS but returns zero alerts is ambiguous: either
# every incident genuinely ended, or the feed/parser quietly broke (a layout
# change, a throttled page, an empty 200). Treating it as "everything ended"
# would mark every active alert for that source expired on one bad run — the
# worst failure for a warning tool. So for an empty result, prior alerts are
# only expired once they have gone unseen this long; a real all-clear still
# clears, just not instantly. A non-empty result keeps the immediate rule.
_EMPTY_FEED_EXPIRY_GRACE = timedelta(hours=2)


def _expiry_cutoff(run_started_at: str, empty_feed: bool) -> str:
    """The last_seen_at cutoff below which an active alert counts as gone."""
    if not empty_feed:
        return run_started_at
    started = datetime.fromisoformat(run_started_at)
    return (started - _EMPTY_FEED_EXPIRY_GRACE).isoformat()


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


def _record_email_failure(alert_id: str) -> None:
    """Stamp alerts.emergency_email_failed_at (migration 0243) and, when known,
    the reason (migration 0245) so the workbench shows 'Email FAILED' and why,
    rather than 'not sent yet'. Best-effort: never raises. If the reason column
    is not there yet the timestamp is still written."""
    now = datetime.now(timezone.utc).isoformat()
    reason = _resend_email.last_failure
    try:
        _supabase_request("PATCH", f"alerts?id=eq.{alert_id}", body={"emergency_email_failed_at": now, "emergency_email_failure_reason": reason})
        return
    except Exception as exc:  # noqa: BLE001 - fall back to the timestamp alone before giving up
        log.warning("[emergency-alerts] could not record email failure reason for alert %s (retrying without it): %s", alert_id, exc)
    try:
        _supabase_request("PATCH", f"alerts?id=eq.{alert_id}", body={"emergency_email_failed_at": now})
    except Exception as exc:  # noqa: BLE001 - recording a failure must never break the ingestion run it is attached to
        log.warning("[emergency-alerts] could not record email failure for alert %s: %s", alert_id, exc)


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
            "&select=id,headline,jurisdiction,alert_type,severity,location,description,canonical_url,issued_at,latitude,longitude"
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

    try:
        sites = site_matching.list_active_sites()
    except Exception as exc:  # noqa: BLE001 - a site-register failure must never block a real emergency warning email; degrade to "no site context"
        log.warning("[emergency-alerts] %s: failed to read alert_sites (sending without site context): %s", source_key, exc)
        sites = []

    sent = 0
    for row in rows:
        silenced = alert_silences.check_silence(
            {"jurisdiction": row["jurisdiction"], "alert_type": row.get("alert_type"), "severity": "emergency_warning", "source_key": source_key},
            active_silences,
        )
        if silenced:
            log.info("[emergency-alerts] %s: alert %s silenced (%s) — email suppressed", source_key, row["id"], silenced.get("reason"))
            continue

        matches = site_matching.match_alert({**row, "severity": "emergency_warning"}, sites)
        tier1 = sum(1 for m in matches if m.site.get("priority") == "Tier 1")
        site_prefix = f"[{len(matches)} site{'s' if len(matches) != 1 else ''} possibly affected{f', {tier1} Tier 1' if tier1 else ''}] " if matches else ""
        subject = f"🚨 {site_prefix}EMERGENCY WARNING — {row['jurisdiction']} — {row['headline']}"
        html = (
            f"<p><strong>{row['headline']}</strong></p>"
            f"<p>Jurisdiction: {row['jurisdiction']}<br>"
            f"Location: {row.get('location') or '—'}<br>"
            f"Issued: {row.get('issued_at') or '—'}</p>"
            f"<p>{row.get('description') or ''}</p>"
            + (f"<p><a href=\"{row['canonical_url']}\">Official source</a></p>" if row.get("canonical_url") else "")
            + _sites_html(matches, bool(sites))
        )
        if not send_email(to=_EMERGENCY_EMAIL_TO, subject=subject, html=html):
            log.warning("[emergency-alerts] %s: email send failed for alert %s — will retry next run (dedupe flag not set)", source_key, row["id"])
            _record_email_failure(row["id"])
            continue
        try:
            _supabase_request("PATCH", f"alerts?id=eq.{row['id']}", body={"emergency_email_sent_at": datetime.now(timezone.utc).isoformat()})
            sent += 1
        except Exception as exc:  # noqa: BLE001 - per-alert notification-flag write inside a loop — one bad write must not abort the batch, already logged with the alert id
            log.warning("[emergency-alerts] %s: sent email but failed to mark alert %s notified — may re-send next run: %s", source_key, row["id"], exc)
    return sent


_BOM_EMAIL_DESCRIPTION_CHARS = 1500


def _send_bom_attention_emails(source_key: str) -> int:
    """Email for each active BOM warning whose platform-assigned attention
    level is "high" (core/platform/bom_attention.py) and that hasn't been
    emailed yet (alerts.emergency_email_sent_at is null — the same persistent
    dedupe as Emergency Warnings).

    BOM warnings carry no AWS tier, so these stay severity 'unknown' in the
    database and the email says plainly that the "high attention" label is
    this platform's own, not BOM's. BOM names a district, not a place, so
    per-site matching is coarse: sites whose suburb/postcode is named in the
    warning are listed, plus how many of our sites are in the affected state.
    Silences, the unreadable-register fallback and the "never raises" rule
    match _send_emergency_warning_emails."""
    try:
        rows = supabase_get(
            f"alerts?source_key=eq.{source_key}&severity=eq.unknown&is_active=eq.true&emergency_email_sent_at=is.null"
            "&select=id,headline,jurisdiction,alert_type,location,description,raw_text,issued_at,latitude,longitude"
        )
    except Exception as exc:  # noqa: BLE001 - best-effort unnotified-BOM read, already logged; caller treats 0 as 'nothing to notify'
        log.warning("[emergency-alerts] %s: failed to read unnotified BOM warnings: %s", source_key, exc)
        return 0
    rows = [r for r in rows or [] if bom_attention.attention_level(r.get("headline"), r.get("alert_type")) == bom_attention.HIGH]
    if not rows:
        return 0

    try:
        active_silences = alert_silences.list_active_silences()
    except Exception as exc:  # noqa: BLE001 - a silence-lookup failure must never block a warning email; degrade to "no active silences"
        log.warning("[emergency-alerts] %s: failed to read active silences (proceeding as if none): %s", source_key, exc)
        active_silences = []
    try:
        sites = site_matching.list_active_sites()
    except Exception as exc:  # noqa: BLE001 - a site-register failure must never block a warning email; degrade to "no site context"
        log.warning("[emergency-alerts] %s: failed to read alert_sites (sending without site context): %s", source_key, exc)
        sites = []

    sent = 0
    for row in rows:
        silenced = alert_silences.check_silence(
            {"jurisdiction": row["jurisdiction"], "alert_type": row.get("alert_type"), "severity": "unknown", "source_key": source_key},
            active_silences,
        )
        if silenced:
            log.info("[emergency-alerts] %s: BOM alert %s silenced (%s) — email suppressed", source_key, row["id"], silenced.get("reason"))
            continue

        matches = site_matching.match_alert({**row, "severity": "unknown"}, sites)
        state = site_matching.state_site_summary(row["jurisdiction"], sites) if sites else {"total": 0, "tier1": 0}
        subject = f"⚠️ BOM WARNING — {row['jurisdiction']} — {row['headline']}"
        source_link = next((line.strip() for line in (row.get("raw_text") or "").splitlines()[::-1] if line.strip().startswith("http")), None)
        text = (row.get("description") or "").strip()
        if len(text) > _BOM_EMAIL_DESCRIPTION_CHARS:
            text = text[:_BOM_EMAIL_DESCRIPTION_CHARS].rstrip() + "…"
        tier1_note = f" ({state['tier1']} Tier 1)" if state["tier1"] else ""
        state_line = (
            f"<p><strong>Our sites in {html.escape(row['jurisdiction'])}:</strong> {state['total']}{tier1_note}. "
            "BOM names districts, not places — check the warning to see whether they are inside the affected area.</p>"
            if state["total"] else ""
        )
        body = (
            f"<p><strong>{html.escape(row['headline'])}</strong></p>"
            f"<p>Jurisdiction: {html.escape(row['jurisdiction'])}<br>Issued: {html.escape(str(row.get('issued_at') or '—'))}</p>"
            "<p><em>The Bureau of Meteorology does not give this warning an Advice / Watch and Act / Emergency Warning "
            "tier. “High attention” is this platform’s own label, chosen from the warning type.</em></p>"
            f"<p>{html.escape(text).replace(chr(10), '<br>')}</p>"
            + (f'<p><a href="{html.escape(source_link, quote=True)}">Official BOM warning</a></p>' if source_link else "")
            + state_line
            + (_sites_html(matches, bool(sites)) if matches else "")
        )
        if not send_email(to=_EMERGENCY_EMAIL_TO, subject=subject, html=body):
            log.warning("[emergency-alerts] %s: BOM email send failed for alert %s — will retry next run (dedupe flag not set)", source_key, row["id"])
            _record_email_failure(row["id"])
            continue
        try:
            _supabase_request("PATCH", f"alerts?id=eq.{row['id']}", body={"emergency_email_sent_at": datetime.now(timezone.utc).isoformat()})
            sent += 1
        except Exception as exc:  # noqa: BLE001 - per-alert notification-flag write inside a loop — one bad write must not abort the batch, already logged with the alert id
            log.warning("[emergency-alerts] %s: sent BOM email but failed to mark alert %s notified — may re-send next run: %s", source_key, row["id"], exc)
    return sent


_MAX_SITES_IN_EMAIL = 15


def _sites_html(matches: list, have_sites: bool) -> str:
    """Own sites this alert may affect, highest-priority first. States the
    basis of each match (distance vs named suburb/postcode) and that no match
    is not proof of safety — regional warnings name a district, not a site.
    Empty when the site register could not be read."""
    if not have_sites:
        return ""
    if not matches:
        return ("<p><strong>Sites:</strong> none matched by location. A regional warning may still "
                "affect sites in this area — check the official source.</p>")
    items = "".join(
        f"<li>{html.escape(m.site.get('priority') or '')} · {html.escape(m.site.get('site_type') or '')} · "
        f"{html.escape(m.site.get('name') or '')}, {html.escape(m.site.get('suburb') or '')} {html.escape(m.site.get('state') or '')} "
        f"— {html.escape(m.reason)}</li>"
        for m in matches[:_MAX_SITES_IN_EMAIL]
    )
    more = f"<p>…and {len(matches) - _MAX_SITES_IN_EMAIL} more.</p>" if len(matches) > _MAX_SITES_IN_EMAIL else ""
    return f"<p><strong>Sites possibly affected ({len(matches)}):</strong></p><ul>{items}</ul>{more}"


_RETIRED_FEED_RE = re.compile(
    r"\b(feed|endpoint|api|data service|web service)\b.{0,40}\b(retire[d]?|retirement|decommission(?:ed)?|discontinued|deprecated|no longer (?:available|supported|updated|maintained))\b"
    r"|\b(retirement|decommission(?:ing)?|discontinuation)\s+notice\b",
    re.IGNORECASE,
)


def feed_retirement_notice(alerts: list) -> str | None:
    """A feed that has been retired sometimes keeps serving a valid document whose
    only 'alert' is the retirement notice (SA CFS did, 2026-08). Treated as a feed
    failure so the heartbeat goes red instead of showing a healthy source with a
    phantom alert. Checks headlines only, with feed-specific wording, so a real
    alert is not caught by an ordinary word like 'discontinued'."""
    for a in alerts:
        headline = getattr(a, "headline", "") or ""
        if _RETIRED_FEED_RE.search(headline):
            return headline[:120]
    return None


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

    notice = feed_retirement_notice(alerts)
    if notice:
        latency_ms = int((time.monotonic() - t0) * 1000)
        message = f"feed appears retired - source returned: {notice}"
        record_heartbeat(domain_key, status="failed", error_message=message[:500], latency_ms=latency_ms)
        log.warning("[emergency-alerts] %s: %s", source_key, message)
        return {"source_key": source_key, "error": message, "count": 0}

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

    expired = 0 if batched else _expire_stale(source_key, _expiry_cutoff(run_started_at, empty_feed=not rows))
    # Only look for unsent emergency warnings when this run's feed actually
    # carries an active one. Every unsent row the query could return is an
    # active emergency_warning for this source, and a still-active alert is
    # re-upserted on every run — so this still retries failed sends and
    # picks up alerts whose silence has expired, without a GET per source
    # per run (~1.4k/day) when there are none (the overwhelmingly common case).
    has_active_warning = any(r["severity"] == "emergency_warning" and r["is_active"] for r in rows)
    emails_sent = _send_emergency_warning_emails(source_key) if has_active_warning else 0
    # BOM warnings have no AWS tier (severity stays 'unknown'), so they never
    # reach the Emergency Warning path above; high-attention ones get their own.
    if source_key.startswith("bom_") and any(
        r["is_active"] and r["severity"] == "unknown" and bom_attention.attention_level(r.get("headline"), r.get("alert_type")) == bom_attention.HIGH
        for r in rows
    ):
        emails_sent += _send_bom_attention_emails(source_key)

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
    # Group by whether the feed came back empty (see _EMPTY_FEED_EXPIRY_GRACE):
    # one expiry pass per group, so the common all-non-empty tick is still a
    # single read + PATCH.
    empty_keys = [key for key in pending if results[key].get("count", 0) == 0]
    normal_keys = [key for key in pending if key not in empty_keys]
    expired = _expire_stale_many(normal_keys, _expiry_cutoff(run_started_at, empty_feed=False))
    if empty_keys:
        expired.update(_expire_stale_many(empty_keys, _expiry_cutoff(run_started_at, empty_feed=True)))
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
    if n_rows == 0:
        detail += " (empty feed — earlier alerts held up to 2h before expiring)"
    if emails_sent:
        detail += f", {emails_sent} emergency email(s) sent"
    return detail


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_all(), indent=2, default=str))
