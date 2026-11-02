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
import alert_email
import alert_silences
import bom_attention
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
# Optional second recipient (e.g. the Captain, while the team mailbox is primary).
_EMERGENCY_EMAIL_CC = os.environ.get("EMERGENCY_ALERT_EMAIL_CC") or None


def _deliver(subject: str, html: str) -> bool:
    """Every alert email goes through here so recipients are set in one place."""
    text = alert_email.html_to_text(html)
    if _EMERGENCY_EMAIL_CC:
        return send_email(to=_EMERGENCY_EMAIL_TO, subject=subject, html=html, cc=_EMERGENCY_EMAIL_CC, text=text)
    return send_email(to=_EMERGENCY_EMAIL_TO, subject=subject, html=html, text=text)

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


def _record_send_meta(row: dict, severity: str) -> None:
    """What was true when we last emailed this alert (tier, wording, time), so a
    later escalation or a material change can be told apart from no change.
    Separate best-effort write (migration 0246): the sent flag never depends on
    these columns existing."""
    try:
        _supabase_request("PATCH", f"alerts?id=eq.{row['id']}", body={
            "emergency_email_tier": severity,
            "emergency_email_hash": alert_email.content_hash(row),
            "emergency_email_last_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:  # noqa: BLE001 - metadata only; follow-up emails baseline themselves if it is missing
        log.warning("[emergency-alerts] could not record email metadata for alert %s: %s", row.get("id"), exc)


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

    sent = 0
    for row in rows:
        silenced = alert_silences.check_silence(
            {"jurisdiction": row["jurisdiction"], "alert_type": row.get("alert_type"), "severity": "emergency_warning", "source_key": source_key},
            active_silences,
        )
        if silenced:
            log.info("[emergency-alerts] %s: alert %s silenced (%s) — email suppressed", source_key, row["id"], silenced.get("reason"))
            continue

        subject = alert_email.build_subject(alert_email.EW, row["jurisdiction"], row["headline"])
        body = (
            alert_email.fields_block(alert_email.EW, {**row, "severity": "emergency_warning", "source_key": source_key})
            + f"<p>{html.escape(row.get('description') or '')}</p>"
            + _official_link_html({**row, "source_key": source_key})
        )
        if not _deliver(subject, body):
            log.warning("[emergency-alerts] %s: email send failed for alert %s — will retry next run (dedupe flag not set)", source_key, row["id"])
            _record_email_failure(row["id"])
            continue
        try:
            _supabase_request("PATCH", f"alerts?id=eq.{row['id']}", body={"emergency_email_sent_at": datetime.now(timezone.utc).isoformat()})
            sent += 1
        except Exception as exc:  # noqa: BLE001 - per-alert notification-flag write inside a loop — one bad write must not abort the batch, already logged with the alert id
            log.warning("[emergency-alerts] %s: sent email but failed to mark alert %s notified — may re-send next run: %s", source_key, row["id"], exc)
            continue
        _record_send_meta(row, "emergency_warning")
    return sent


def _send_watch_and_act_emails(source_key: str) -> int:
    """Email for each active Watch and Act alert that has not been emailed yet.
    Same dedupe column, silences, never-raises and failure-recording rules as
    Emergency Warnings (a Watch and Act CAN be silenced; an Emergency Warning
    cannot). No site matching: the mailbox's reader decides what it means for us."""
    try:
        rows = supabase_get(
            f"alerts?source_key=eq.{source_key}&severity=eq.watch_and_act"
            "&is_active=eq.true&emergency_email_sent_at=is.null"
            "&select=id,headline,jurisdiction,alert_type,severity,location,description,canonical_url,issued_at,latitude,longitude"
        )
    except Exception as exc:  # noqa: BLE001 - best-effort read, already logged; caller treats 0 as 'nothing to notify'
        log.warning("[emergency-alerts] %s: failed to read unnotified Watch and Act alerts: %s", source_key, exc)
        return 0
    if not rows:
        return 0
    try:
        active_silences = alert_silences.list_active_silences()
    except Exception as exc:  # noqa: BLE001 - a silence-lookup failure must not block a warning email; degrade to "no active silences"
        log.warning("[emergency-alerts] %s: failed to read active silences (proceeding as if none): %s", source_key, exc)
        active_silences = []

    sent = 0
    for row in rows:
        if alert_silences.check_silence(
            {"jurisdiction": row["jurisdiction"], "alert_type": row.get("alert_type"), "severity": "watch_and_act", "source_key": source_key},
            active_silences,
        ):
            continue
        subject = alert_email.build_subject(alert_email.WA, row["jurisdiction"], row["headline"])
        body = (
            alert_email.fields_block(alert_email.WA, {**row, "severity": "watch_and_act", "source_key": source_key})
            + f"<p>{html.escape(row.get('description') or '')}</p>"
            + _official_link_html({**row, "source_key": source_key})
        )
        if not _deliver(subject, body):
            log.warning("[emergency-alerts] %s: Watch and Act email failed for alert %s — will retry next run", source_key, row["id"])
            _record_email_failure(row["id"])
            continue
        try:
            _supabase_request("PATCH", f"alerts?id=eq.{row['id']}", body={"emergency_email_sent_at": datetime.now(timezone.utc).isoformat()})
            sent += 1
        except Exception as exc:  # noqa: BLE001 - per-alert flag write inside a loop; one bad write must not abort the batch
            log.warning("[emergency-alerts] %s: sent Watch and Act email but failed to mark alert %s notified: %s", source_key, row["id"], exc)
            continue
        _record_send_meta(row, "watch_and_act")
    return sent


_BOM_EMAIL_DESCRIPTION_CHARS = 3500


def _send_bom_attention_emails(source_key: str) -> int:
    """Email for each active BOM warning whose platform-assigned attention
    level is "high" (core/platform/bom_attention.py) and that hasn't been
    emailed yet (alerts.emergency_email_sent_at is null — the same persistent
    dedupe as Emergency Warnings).

    BOM warnings carry no AWS tier, so these stay severity 'unknown' in the
    database and the email says plainly that the "high attention" label is
    this platform's own, not BOM's. Every high-attention warning is emailed; no
    site matching (the mailbox's reader decides what it means for us). Silences
    and the "never raises" rule match _send_emergency_warning_emails."""
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
    sent = 0
    for row in rows:
        silenced = alert_silences.check_silence(
            {"jurisdiction": row["jurisdiction"], "alert_type": row.get("alert_type"), "severity": "unknown", "source_key": source_key},
            active_silences,
        )
        if silenced:
            log.info("[emergency-alerts] %s: BOM alert %s silenced (%s) — email suppressed", source_key, row["id"], silenced.get("reason"))
            continue

        subject = alert_email.build_subject(alert_email.BOM_HIGH, row["jurisdiction"], row["headline"])
        source_link = next((line.strip() for line in (row.get("raw_text") or "").splitlines()[::-1] if line.strip().startswith("http")), None)
        text = _clean_bom_text(row.get("description") or "")
        body = (
            alert_email.fields_block(alert_email.BOM_HIGH, {**row, "severity": "unknown", "source_key": source_key, "canonical_url": source_link, "issued_at": _issued_text(row) if _issued_text(row) != "-" else None})
            + "<p><em>The Bureau of Meteorology does not give this warning an Advice / Watch and Act / Emergency Warning "
            "tier. “High attention” is this platform’s own label, chosen from the warning type.</em></p>"
            f"<p>{html.escape(text).replace(chr(10), '<br>')}</p>"
            + _official_link_html({**row, "source_key": source_key, "canonical_url": source_link}, "Official BOM warning")
        )
        if not _deliver(subject, body):
            log.warning("[emergency-alerts] %s: BOM email send failed for alert %s — will retry next run (dedupe flag not set)", source_key, row["id"])
            _record_email_failure(row["id"])
            continue
        try:
            _supabase_request("PATCH", f"alerts?id=eq.{row['id']}", body={"emergency_email_sent_at": datetime.now(timezone.utc).isoformat()})
            sent += 1
        except Exception as exc:  # noqa: BLE001 - per-alert notification-flag write inside a loop — one bad write must not abort the batch, already logged with the alert id
            log.warning("[emergency-alerts] %s: sent BOM email but failed to mark alert %s notified — may re-send next run: %s", source_key, row["id"], exc)
            continue
        _record_send_meta(row, "unknown")
    return sent


def _official_link_html(row: dict, label: str = "Official source") -> str:
    """The best page a person can open for this alert, said honestly: a link to a page
    that LISTS current incidents (NSW RFS, ACT ESA, SA CFS) is labelled as a list, and the
    exact data record, where there is one, is offered separately."""
    official, record, precision = alert_email.official_links(row)
    parts = []
    if official:
        text = label if precision == "direct" else f"{label} (current incidents list - find this alert on it)"
        parts.append(f'<a href="{html.escape(official, quote=True)}">{html.escape(text)}</a>')
    if record:
        parts.append(f'<a href="{html.escape(record, quote=True)}">Data record for this alert</a>')
    return f"<p>{' · '.join(parts)}</p>" if parts else ""


def _clean_bom_text(text: str) -> str:
    """BOM descriptions are scraped from the warning page and start with site
    navigation ("Warnings Information / About Severe Weather Warning Services /
    IDV21033 / Australian Government Bureau of Meteorology"). Start at the warning
    itself, drop runs of blank lines, and if it is long cut at a paragraph end
    rather than mid-sentence."""
    text = (text or "").strip()
    for marker in (r"TOP PRIORITY[^\n]*\n", r"Australian Government Bureau of Meteorology[^\n]*\n"):
        m = re.search(marker, text)
        if m:
            text = text[m.end():]
            break
    text = re.sub(r"\n\s*\n(\s*\n)+", "\n\n", text).strip()
    if len(text) > _BOM_EMAIL_DESCRIPTION_CHARS:
        cut = text.rfind("\n\n", 0, _BOM_EMAIL_DESCRIPTION_CHARS)
        text = text[: cut if cut > _BOM_EMAIL_DESCRIPTION_CHARS // 2 else _BOM_EMAIL_DESCRIPTION_CHARS].rstrip() + "\n\n[Shortened - see the official warning for the full text.]"
    return text


def _issued_text(row: dict) -> str:
    """BOM rows have no structured issue time; the warning text says "Issued at 2:38 pm Monday, 2 November 2026."."""
    if row.get("issued_at"):
        return str(row["issued_at"])
    m = re.search(r"Issued at ([^\n]+?)\.?\s*(?:\n|$)", row.get("description") or "")
    return m.group(1).strip() if m else "-"


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
    if any(r["severity"] == "watch_and_act" and r["is_active"] for r in rows):
        emails_sent += _send_watch_and_act_emails(source_key)
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


_FOLLOW_UP_WINDOW = timedelta(hours=6)
_UPDATE_MIN_INTERVAL = timedelta(minutes=30)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _still_high_bom(row: dict) -> bool:
    return not row["source_key"].startswith("bom_") or bom_attention.attention_level(row.get("headline"), row.get("alert_type")) == bom_attention.HIGH


def _send_follow_up_emails(now: datetime | None = None) -> dict:
    """[UPDATE] and [LIFTED] emails for alerts we have already emailed, from ONE
    read per run (alerts emailed and seen in the last 6 hours).

      UPDATE   the alert escalated (e.g. Watch and Act -> Emergency Warning), or its
               wording materially changed (at most one every 30 minutes).
      LIFTED   the alert is no longer active; sent once. Says only that the source
               stopped listing it, which is NOT an all-clear.

    Alerts emailed before migration 0246 have no stored tier: they are baselined
    silently, never emailed retroactively. Watch and Act / BOM can be silenced;
    an Emergency Warning cannot. Never raises."""
    now = now or datetime.now(timezone.utc)
    cutoff = urllib.parse.quote((now - _FOLLOW_UP_WINDOW).isoformat())
    try:
        rows = supabase_get(
            f"alerts?emergency_email_sent_at=not.is.null&last_seen_at=gte.{cutoff}&limit=500"
            "&select=id,source_key,headline,jurisdiction,alert_type,severity,location,description,canonical_url,issued_at,is_active,"
            "emergency_email_tier,emergency_email_hash,emergency_email_last_at,emergency_email_lifted_at"
        )
    except Exception as exc:  # noqa: BLE001 - follow-ups are best-effort (also fails safe while migration 0246 is not applied)
        log.warning("[emergency-alerts] follow-up read failed: %s", exc)
        return {"updates": 0, "lifted": 0}
    if not rows:
        return {"updates": 0, "lifted": 0}
    try:
        active_silences = alert_silences.list_active_silences()
    except Exception as exc:  # noqa: BLE001 - degrade to "no active silences"
        log.warning("[emergency-alerts] follow-up: failed to read active silences: %s", exc)
        active_silences = []
    counts = {"updates": 0, "lifted": 0}
    stamp = now.isoformat()
    for row in rows:
        recorded = row.get("emergency_email_tier")
        if not row.get("is_active"):
            if row.get("emergency_email_lifted_at"):
                continue
            if not recorded:  # predates 0246: close it out silently
                _patch_alert(row["id"], {"emergency_email_lifted_at": stamp})
                continue
            if _send_lifted(row, stamp):
                counts["lifted"] += 1
            continue
        if not recorded:  # predates 0246: baseline silently
            _record_send_meta(row, row["severity"])
            continue
        if not _still_high_bom(row):
            continue
        change = None
        if alert_email.tier_rank(row["severity"]) > alert_email.tier_rank(recorded):
            change = f"Escalated from {alert_email.TIER_LABEL.get(recorded, recorded)} to {alert_email.TIER_LABEL.get(row['severity'], row['severity'])}"
        elif row.get("emergency_email_hash") and alert_email.content_hash(row) != row["emergency_email_hash"]:
            last = _parse_ts(row.get("emergency_email_last_at"))
            if last is None or now - last >= _UPDATE_MIN_INTERVAL:
                change = "Wording updated"
        if not change:
            continue
        if row["severity"] != "emergency_warning" and alert_silences.check_silence(
            {"jurisdiction": row["jurisdiction"], "alert_type": row.get("alert_type"), "severity": row["severity"], "source_key": row["source_key"]},
            active_silences,
        ):
            continue
        body = (
            alert_email.fields_block(alert_email.UPDATE, row, {"Change": change})
            + f"<p><strong>{html.escape(change)}</strong></p>"
            f"<p>{html.escape(row.get('description') or '')}</p>"
            + _official_link_html(row)
        )
        if not _deliver(alert_email.build_subject(alert_email.UPDATE, row["jurisdiction"], row["headline"]), body):
            log.warning("[emergency-alerts] follow-up: update email failed for alert %s - will retry next run", row["id"])
            continue
        _record_send_meta(row, row["severity"])
        counts["updates"] += 1
    return counts


def _patch_alert(alert_id: str, body: dict) -> bool:
    try:
        _supabase_request("PATCH", f"alerts?id=eq.{alert_id}", body=body)
        return True
    except Exception as exc:  # noqa: BLE001 - per-alert write inside a loop; logged with the alert id
        log.warning("[emergency-alerts] could not update alert %s: %s", alert_id, exc)
        return False


def _send_lifted(row: dict, stamp: str) -> bool:
    body = (
        alert_email.fields_block(alert_email.LIFTED, row, {"Listed-Until": stamp})
        + f"<p><strong>No longer listed by the source:</strong> {html.escape(row['headline'])}</p>"
        "<p>The source has stopped listing this alert. <strong>This is not an all-clear</strong>: check the official source "
        "before treating the situation as over.</p>"
        + _official_link_html(row)
    )
    if not _deliver(alert_email.build_subject(alert_email.LIFTED, row["jurisdiction"], row["headline"]), body):
        log.warning("[emergency-alerts] follow-up: lifted email failed for alert %s - will retry next run", row["id"])
        return False
    return _patch_alert(row["id"], {"emergency_email_lifted_at": stamp})


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
    results["_follow_up"] = _send_follow_up_emails()
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
