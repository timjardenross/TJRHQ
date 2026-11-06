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
import alert_schema
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


def _recipients(tag: str | None) -> tuple[str, str | None]:
    """(to, cc) for an email tag. EMERGENCY_ALERT_EMAIL_TO_<TAG> / EMERGENCY_ALERT_EMAIL_CC_<TAG> (TAG upper-case, "-" as "_",
    e.g. EMERGENCY_ALERT_EMAIL_TO_EW, ..._CC_BOM_HIGH) override the defaults for that kind of email only, so, say,
    Emergency Warnings can reach more people than Watch and Act. Unset = the defaults, exactly as before."""
    if tag:
        suffix = tag.upper().replace("-", "_")
        to = os.environ.get(f"EMERGENCY_ALERT_EMAIL_TO_{suffix}") or _EMERGENCY_EMAIL_TO
        cc = os.environ.get(f"EMERGENCY_ALERT_EMAIL_CC_{suffix}") or _EMERGENCY_EMAIL_CC
        return to, cc
    return _EMERGENCY_EMAIL_TO, _EMERGENCY_EMAIL_CC


def _deliver(subject: str, html: str, tag: str | None = None) -> bool:
    """Every alert email goes through here so recipients are set in one place (per-tag overrides: _recipients)."""
    text = alert_email.html_to_text(html)
    to, cc = _recipients(tag)
    if cc:
        return send_email(to=to, subject=subject, html=html, cc=cc, text=text)
    return send_email(to=to, subject=subject, html=html, text=text)

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


def _supabase_request(method: str, path: str, body: dict | list | None = None, extra_headers: dict | None = None, timeout: int = 15) -> None:
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


# CAP fields CanonicalAlert carries for sources that provide them (SA, VIC
# warnings). They are alerts columns since migration 0250, applied to the
# USSTJR project 2026-11-06, so they are stored by default. Setting
# EMERGENCY_ALERTS_CAP_FIELDS to 0/false/off/no strips them from the upsert
# again: an escape hatch for a database that does NOT have the columns (an
# unknown column fails the whole source's upsert in PostgREST).
_CAP_FIELDS = ("cap_urgency", "cap_certainty", "cap_severity", "cap_event")
_CAP_FIELDS_OFF_VALUES = frozenset({"0", "false", "off", "no"})


def _cap_fields_enabled() -> bool:
    """On unless explicitly switched off. Read per run (not at import) so it takes
    effect without code changes. Unset or empty means on."""
    return os.environ.get("EMERGENCY_ALERTS_CAP_FIELDS", "").strip().lower() not in _CAP_FIELDS_OFF_VALUES


def _cap_select() -> str:
    """Extra columns for the email queries so the header can carry the CAP fields. Left out when the CAP flag is
    off, because that is the escape hatch for a database without those columns (a select naming them would fail)."""
    return "," + ",".join(_CAP_FIELDS) if _cap_fields_enabled() else ""


def _coerce_rows(source_key: str, rows: list[dict]) -> tuple[int, int]:
    """Make every row safe for the alerts CHECK constraints (alert_schema).

    An out-of-set alert_type becomes 'other' and an out-of-set severity
    'unknown'. The row is NEVER dropped: _upsert_batch is one request per
    source, so one invalid value would fail every row in it, and dropping the
    row instead would make a live alert look gone (-> expired -> false
    "lifted"). Logs source_key and the bad value only (no other row content).
    Returns (alert_type_coerced, severity_coerced)."""
    n_type = n_severity = 0
    for row in rows:
        if row.get("alert_type") not in alert_schema.ALLOWED_ALERT_TYPE:
            log.warning("[emergency-alerts] %s: alert_type %r is not in the alerts schema - coerced to %r", source_key, str(row.get("alert_type"))[:60], alert_schema.DEFAULT_ALERT_TYPE)
            row["alert_type"] = alert_schema.DEFAULT_ALERT_TYPE
            n_type += 1
        if row.get("severity") not in alert_schema.ALLOWED_SEVERITY:
            log.warning("[emergency-alerts] %s: severity %r is not in the alerts schema - coerced to %r", source_key, str(row.get("severity"))[:60], alert_schema.DEFAULT_SEVERITY)
            row["severity"] = alert_schema.DEFAULT_SEVERITY
            n_severity += 1
    return n_type, n_severity


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
            "&select=id,headline,jurisdiction,alert_type,severity,location,description,canonical_url,issued_at,latitude,longitude" + _cap_select()
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
        if not _deliver(subject, body, alert_email.EW):
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
            "&select=id,headline,jurisdiction,alert_type,severity,location,description,canonical_url,issued_at,latitude,longitude" + _cap_select()
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
        if not _deliver(subject, body, alert_email.WA):
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


def _advice_rules() -> list[tuple[str, str]]:
    """EMERGENCY_ALERT_ADVICE_EMAIL="NSW:flood,*:bushfire" switches Advice emails on for those jurisdiction:hazard pairs.
    Unset (the default) = no Advice emails; Advice stays in the daily digest only. Read per run."""
    return alert_email.parse_advice_rules(os.environ.get("EMERGENCY_ALERT_ADVICE_EMAIL"))


def _send_advice_emails(source_key: str, rules: list[tuple[str, str]]) -> int:
    """Email for each active Advice alert matching an opted-in jurisdiction:hazard rule that has not been emailed yet.
    Same dedupe column, silences (Advice CAN be silenced), never-raises and failure-recording rules as Watch and Act.
    Advice churns, so these alerts get no UPDATE (except an escalation) or LIFTED follow-ups."""
    try:
        rows = supabase_get(
            f"alerts?source_key=eq.{source_key}&severity=eq.advice"
            "&is_active=eq.true&emergency_email_sent_at=is.null"
            "&select=id,headline,jurisdiction,alert_type,severity,location,description,canonical_url,issued_at,latitude,longitude" + _cap_select()
        )
    except Exception as exc:  # noqa: BLE001 - best-effort read, already logged; caller treats 0 as 'nothing to notify'
        log.warning("[emergency-alerts] %s: failed to read unnotified Advice alerts: %s", source_key, exc)
        return 0
    rows = [r for r in rows or [] if alert_email.advice_matches(rules, r.get("jurisdiction"), r.get("alert_type"))]
    if not rows:
        return 0
    try:
        active_silences = alert_silences.list_active_silences()
    except Exception as exc:  # noqa: BLE001 - a silence-lookup failure must not block an email; degrade to "no active silences"
        log.warning("[emergency-alerts] %s: failed to read active silences (proceeding as if none): %s", source_key, exc)
        active_silences = []
    sent = 0
    for row in rows:
        if alert_silences.check_silence(
            {"jurisdiction": row["jurisdiction"], "alert_type": row.get("alert_type"), "severity": "advice", "source_key": source_key},
            active_silences,
        ):
            continue
        subject = alert_email.build_subject(alert_email.ADVICE, row["jurisdiction"], row["headline"])
        body = (
            alert_email.fields_block(alert_email.ADVICE, {**row, "severity": "advice", "source_key": source_key})
            + f"<p>{html.escape(row.get('description') or '')}</p>"
            + _official_link_html({**row, "source_key": source_key})
        )
        if not _deliver(subject, body, alert_email.ADVICE):
            log.warning("[emergency-alerts] %s: Advice email failed for alert %s - will retry next run", source_key, row["id"])
            _record_email_failure(row["id"])
            continue
        try:
            _supabase_request("PATCH", f"alerts?id=eq.{row['id']}", body={"emergency_email_sent_at": datetime.now(timezone.utc).isoformat()})
            sent += 1
        except Exception as exc:  # noqa: BLE001 - per-alert flag write inside a loop; one bad write must not abort the batch
            log.warning("[emergency-alerts] %s: sent Advice email but failed to mark alert %s notified: %s", source_key, row["id"], exc)
            continue
        _record_send_meta(row, "advice")
    return sent


_BOM_EMAIL_DESCRIPTION_CHARS = 3500


_DUPLICATE_TIER = "duplicate"


def _already_emailed_elsewhere(row: dict) -> bool:
    """True when another alert row (the same BOM product listed by another state feed) has
    already been emailed. Fails open: if the check errors, the email is sent."""
    product = alert_email.bom_product_id(row)
    if not product:
        return False
    try:
        found = supabase_get(
            f"alerts?description=like.*{product}*&emergency_email_sent_at=not.is.null&id=neq.{row['id']}"
            f"&emergency_email_tier=neq.{_DUPLICATE_TIER}&select=id&limit=1"
        )
    except Exception as exc:  # noqa: BLE001 - dedupe is an optimisation; never block a warning on it
        log.warning("[emergency-alerts] duplicate check failed for alert %s: %s", row.get("id"), exc)
        return False
    return bool(found)


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
            "&select=id,headline,jurisdiction,alert_type,location,description,raw_text,issued_at,latitude,longitude" + _cap_select()
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

        if _already_emailed_elsewhere(row):
            log.info("[emergency-alerts] %s: BOM alert %s is the same product as one already emailed - not emailing again", source_key, row["id"])
            _patch_alert(row["id"], {"emergency_email_sent_at": datetime.now(timezone.utc).isoformat(), "emergency_email_tier": _DUPLICATE_TIER})
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
        if not _deliver(subject, body, alert_email.BOM_HIGH):
            log.warning("[emergency-alerts] %s: BOM email send failed for alert %s — will retry next run (dedupe flag not set)", source_key, row["id"])
            _record_email_failure(row["id"])
            continue
        try:
            _supabase_request("PATCH", f"alerts?id=eq.{row['id']}", body={"emergency_email_sent_at": datetime.now(timezone.utc).isoformat()})
            sent += 1
        except Exception as exc:  # noqa: BLE001 - per-alert notification-flag write inside a loop — one bad write must not abort the batch, already logged with the alert id
            log.warning("[emergency-alerts] %s: sent BOM email but failed to mark alert %s notified — may re-send next run: %s", source_key, row["id"], exc)
            continue
        _record_send_meta({**row, "source_key": source_key}, "unknown")
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

    # Adapters that can account for what they skip expose fetch_with_ledger();
    # the rest (and test doubles) keep the plain fetch() contract.
    ledger = None
    try:
        with_ledger = getattr(adapter, "fetch_with_ledger", None)
        if with_ledger is not None:
            alerts, ledger = with_ledger()
        else:
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

    # Integrity gate (before coercion and upsert, and so before any expiry): a
    # feed whose every item failed structural parsing is BROKEN, not quiet.
    # Failing here leaves existing alerts untouched - no expiry is scheduled -
    # so a parser break can never turn live alerts into false "lifted" notices.
    failure, integrity_warning = _ledger_verdict(ledger, accepted=len(alerts))
    if failure:
        latency_ms = int((time.monotonic() - t0) * 1000)
        record_heartbeat(domain_key, status="failed", error_message=failure[:500], latency_ms=latency_ms)
        log.warning("[emergency-alerts] %s: %s", source_key, failure)
        failed = {"source_key": source_key, "error": failure, "count": 0}
        row = _integrity_row(source_key, "failed", ledger, 0, [failure])
        if row and batched:
            failed["_integrity"] = row  # run_all() writes every source's row in one request
        elif row:
            _upsert_integrity([row])
        return failed

    keep_cap = _cap_fields_enabled()
    notes = _integrity_notes(adapter, alerts, ledger)
    for note in notes:
        log.warning("[emergency-alerts] %s: %s", source_key, note)
    warnings = [w for w in (integrity_warning, *notes) if w]
    if notes:
        integrity_warning = " | ".join(warnings)

    rows = []
    for a in alerts:
        row = asdict(a)
        closed = row.pop("closed")  # not a DB column — CanonicalAlert-only signal, see base.py
        if not keep_cap:
            for field in _CAP_FIELDS:  # not alerts columns until migration 0250 is applied; an unknown column fails the whole upsert
                row.pop(field, None)
        row["status"] = "expired" if closed else "active"
        row["is_active"] = not closed
        row["last_seen_at"] = run_started_at
        rows.append(row)

    # After any drop accounting, before the upsert: make every row valid for
    # the CHECK constraints rather than let one bad value fail the batch.
    coerced = _coerce_rows(source_key, rows)

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
    advice_rules = _advice_rules()
    if advice_rules and any(r["severity"] == "advice" and r["is_active"] and alert_email.advice_matches(advice_rules, r.get("jurisdiction"), r.get("alert_type")) for r in rows):
        emails_sent += _send_advice_emails(source_key, advice_rules)
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
    unknown_count = sum(1 for r in rows if r["severity"] == "unknown")
    latency_ms = int((time.monotonic() - t0) * 1000)
    if batched:
        # run_all() fills in detail once its single expiry pass has the count.
        heartbeats.append({
            "domain_key": domain_key, "status": "ok", "latency_ms": latency_ms,
            "_counts": (len(rows), unknown_count, emails_sent, {"coerced": coerced, "ledger": ledger, "warning": integrity_warning}),
        })
    else:
        record_heartbeat(
            domain_key, status="ok",
            detail=_ok_detail(len(rows), unknown_count, expired, emails_sent, coerced=coerced, ledger=ledger, warning=integrity_warning),
            latency_ms=latency_ms,
        )
    result = {
        "source_key": source_key, "count": len(rows), "unknown_severity": unknown_count,
        "expired": expired, "emails_sent": emails_sent, "pending_expiry": batched,
    }
    if ledger is not None:
        result["drops"] = ledger.as_dict()
        row = _integrity_row(source_key, "ok", ledger, len(rows), warnings)
        if batched:
            result["_integrity"] = row
        else:
            _upsert_integrity([row])
    return result


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
            "&select=id,source_key,headline,jurisdiction,alert_type,severity,location,description,canonical_url,issued_at,is_active,first_seen_at,last_seen_at,"
            "emergency_email_tier,emergency_email_hash,emergency_email_last_at,emergency_email_lifted_at" + _cap_select()
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
        if recorded == _DUPLICATE_TIER:  # same BOM product as an alert already emailed: no follow-ups
            continue
        if recorded == "advice" and row.get("severity") == "advice":
            # Advice emails are opt-in and Advice churns: no wording updates and no LIFTED. Just close it out silently.
            if not row.get("is_active") and not row.get("emergency_email_lifted_at"):
                _patch_alert(row["id"], {"emergency_email_lifted_at": stamp})
            continue
        if not row.get("is_active"):
            if row.get("emergency_email_lifted_at"):
                continue
            # predates 0246, or a BOM flood warning (re-issued and withdrawn constantly): close it out silently
            if not recorded or (row["source_key"].startswith("bom_") and "flood" in (row.get("headline") or "").lower()):
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
        elif row.get("emergency_email_hash") and alert_email.hash_version(alert_email.content_hash(row)) != alert_email.hash_version(row["emergency_email_hash"]):
            _record_send_meta(row, recorded)  # hash recipe changed: re-baseline silently, no email
            continue
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
        if not _deliver(alert_email.build_subject(alert_email.UPDATE, row["jurisdiction"], row["headline"]), body, alert_email.UPDATE):
            log.warning("[emergency-alerts] follow-up: update email failed for alert %s - will retry next run", row["id"])
            continue
        _record_send_meta(row, row["severity"])
        counts["updates"] += 1
    return counts


# ---- feed-down / recovery emails ([FEED]) -----------------------------------------------------------------------
# A collector that keeps failing, or whose feed has gone quiet (the STALE integrity warning), emails once when it
# crosses the threshold, again every _FEED_REMINDER_EVERY while it stays down, and once more when it recovers. State
# lives in emergency_alert_feed_state (migration 0254). If that table is not there yet, nothing is emailed and a
# warning is logged: no state means no way to avoid repeating the email every 15 minutes.
_FEED_DOWN_AFTER_FAILED_RUNS = 3  # consecutive failed runs (~45 min at the 15-minute cadence) before a "failed" email
_FEED_REMINDER_EVERY = timedelta(hours=12)


def _source_jurisdiction(source_key: str) -> str:
    if source_key.startswith("bom_"):
        return source_key[4:].upper()
    return {"nsw_rfs": "NSW", "vic_emergency": "VIC", "qld_fire": "QLD", "sa_cfs": "SA", "act_esa": "ACT", "wa_dfes": "WA", "tas_fire": "TAS", "nt_securent": "NT"}.get(source_key, "AU")


def _feed_problem(result: dict, integrity_row: dict | None) -> tuple[str, str] | None:
    """("failed" | "stale", detail) when this run shows the source is down or has gone quiet, else None.
    A skipped (not-yet-implemented) source is neither."""
    if result.get("error"):
        return "failed", str(result["error"])[:300]
    for warning in (integrity_row or {}).get("warnings") or []:
        if str(warning).startswith("STALE"):
            return "stale", str(warning)[:300]
    return None


def _send_feed_down(source_key: str, kind: str, detail: str, since: str, streak: int, reminder: bool) -> bool:
    jurisdiction = _source_jurisdiction(source_key)
    what = f"{streak} failed runs in a row" if kind == "failed" else "its feed has gone quiet"
    headline = f"{source_key} is {'still ' if reminder else ''}not reporting ({what})"
    body = (
        alert_email.feed_block(
            {"source_key": source_key, "jurisdiction": jurisdiction, "problem": kind, "since": since},
            {"Failed-Runs": streak if kind == "failed" else "-", "Detail": detail},
        )
        + f"<p><strong>{html.escape(jurisdiction)} alerts from {html.escape(source_key)} may be missing.</strong> "
        "No alert from this source is being checked while it is down, so a quiet mailbox is NOT reassuring for it.</p>"
        f"<p>{html.escape(detail)}</p>"
    )
    return _deliver(alert_email.build_subject(alert_email.FEED, jurisdiction, headline), body, alert_email.FEED)


def _send_feed_recovered(source_key: str, kind: str, since: str | None, now: datetime) -> bool:
    jurisdiction = _source_jurisdiction(source_key)
    down_for = None
    since_ts = _parse_ts(since)
    if since_ts is not None:
        down_for = alert_email.format_duration(now - since_ts)
    body = (
        alert_email.feed_block({"source_key": source_key, "jurisdiction": jurisdiction, "problem": f"recovered (was {kind})", "since": since},
                               {"Down-For": down_for or "-"})
        + f"<p><strong>{html.escape(source_key)} is reporting again.</strong>"
        + (f" It was down for about {html.escape(down_for)}." if down_for else "")
        + " Alerts issued while it was down may have been missed: check the official source for the period.</p>"
    )
    return _deliver(alert_email.build_subject(alert_email.FEED, jurisdiction, f"{source_key} is reporting again"), body, alert_email.FEED)


def _send_feed_emails(results: dict, integrity: dict[str, dict], now: datetime | None = None) -> dict:
    """One pass per run_all(): update each source's down/quiet streak, email on the threshold, on reminders and on
    recovery. Never raises. Returns {"down": n, "reminders": n, "recovered": n}."""
    counts = {"down": 0, "reminders": 0, "recovered": 0}
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    try:
        states = {row["source_key"]: row for row in supabase_get("emergency_alert_feed_state?select=*") or []}
    except Exception as exc:  # noqa: BLE001 - optional feature: without the state table (migration 0254) there is no safe way to dedupe, so send nothing
        log.warning("[emergency-alerts] feed alerts disabled (emergency_alert_feed_state unavailable - migration 0254 not applied?): %s", exc)
        return counts
    writes: list[dict] = []
    for source_key, result in results.items():
        if source_key.startswith("_") or not isinstance(result, dict):
            continue
        state = states.get(source_key) or {}
        problem = _feed_problem(result, integrity.get(source_key))
        if problem:
            kind, detail = problem
            streak = (state.get("consecutive") or 0) + 1 if state.get("problem") else 1
            since = state.get("since") if state.get("problem") and state.get("since") else stamp
            emailed_at = state.get("emailed_at")
            last = _parse_ts(emailed_at)
            threshold = _FEED_DOWN_AFTER_FAILED_RUNS if kind == "failed" else 1
            due = streak >= threshold and (last is None or now - last >= _FEED_REMINDER_EVERY)
            if due and _send_feed_down(source_key, kind, detail, since, streak, reminder=last is not None):
                counts["reminders" if last is not None else "down"] += 1
                emailed_at = stamp
            writes.append({"source_key": source_key, "problem": kind, "consecutive": streak, "since": since, "emailed_at": emailed_at, "detail": detail, "updated_at": stamp})
        elif state.get("problem"):
            if state.get("emailed_at") and not _send_feed_recovered(source_key, state["problem"], state.get("since"), now):
                continue  # keep the state: retry the recovery email next run
            if state.get("emailed_at"):
                counts["recovered"] += 1
            writes.append({"source_key": source_key, "problem": None, "consecutive": 0, "since": None, "emailed_at": None, "detail": None, "updated_at": stamp})
    if writes:
        try:
            _supabase_request(
                "POST", "emergency_alert_feed_state?on_conflict=source_key", body=writes,
                extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            )
        except Exception as exc:  # noqa: BLE001 - state write failed: the next run will re-evaluate (and may repeat an email); logged, never raised
            log.warning("[emergency-alerts] could not record feed alert state: %s", exc)
    return counts


def _patch_alert(alert_id: str, body: dict) -> bool:
    try:
        _supabase_request("PATCH", f"alerts?id=eq.{alert_id}", body=body)
        return True
    except Exception as exc:  # noqa: BLE001 - per-alert write inside a loop; logged with the alert id
        log.warning("[emergency-alerts] could not update alert %s: %s", alert_id, exc)
        return False


def _listed_for(row: dict) -> str | None:
    """How long the source listed this alert (first time we saw it to the last time it was listed), e.g. "3h 20m"."""
    first, last = _parse_ts(row.get("first_seen_at")), _parse_ts(row.get("last_seen_at"))
    if first is None or last is None or last < first:
        return None
    return alert_email.format_duration(last - first)


def _send_lifted(row: dict, stamp: str) -> bool:
    listed_for = _listed_for(row)
    body = (
        alert_email.fields_block(alert_email.LIFTED, row, {"Listed-Until": stamp, **({"Listed-For": listed_for} if listed_for else {})})
        + f"<p><strong>No longer listed by the source:</strong> {html.escape(row['headline'])}</p>"
        + (f"<p>The source listed it for {html.escape(listed_for)}.</p>" if listed_for else "")
        + "<p>The source has stopped listing this alert. <strong>This is not an all-clear</strong>: check the official source "
        "before treating the situation as over.</p>"
        + _official_link_html(row)
    )
    if not _deliver(alert_email.build_subject(alert_email.LIFTED, row["jurisdiction"], row["headline"]), body, alert_email.LIFTED):
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
            n_rows, unknown_count, emails_sent, extras = counts
            hb["detail"] = _ok_detail(n_rows, unknown_count, expired_by_domain.get(hb["domain_key"], 0), emails_sent, **extras)

    record_heartbeats(heartbeats)
    integrity_rows = {key: row for key, row in ((key, result.pop("_integrity", None)) for key, result in results.items()) if row}
    _upsert_integrity(list(integrity_rows.values()))
    results["_feed_alerts"] = _send_feed_emails(results, integrity_rows)
    results["_follow_up"] = _send_follow_up_emails()
    return results


# A source is only "broken" for parsing reasons above this share of invalid
# items (with some accepted): flagged in the heartbeat detail, status stays ok.
_INVALID_WARN_RATIO = 0.20

# Heartbeat detail is free text (domain_heartbeats.detail, migration 0071); keep
# it bounded like error_message (500). The headline counts come first so a long
# drop breakdown is what gets cut, never the alert counts.
_DETAIL_MAX_CHARS = 500


# A field every kept alert should carry (SOURCE_INFO["expected_fields"]) that is missing
# on ALL of them, across at least this many alerts, means the feed's shape changed under
# the parser (a renamed key quietly reads as None). Below this the sample is too small.
_FIELD_DRIFT_MIN_ALERTS = 3


def _integrity_notes(adapter, alerts: list, ledger, now: datetime | None = None) -> list[str]:
    """Warnings that do NOT fail a source but say its data may be going quiet or changing shape:
      STALE        the newest source-side timestamp across every item looked at (before any
                   exclusion) is older than SOURCE_INFO["stale_after_hours"] - a feed that is
                   fetched and parsed fine but has stopped producing anything new.
      FIELD DRIFT  an expected field is missing on every kept alert.
    Sources with no threshold (quiet by nature) are never flagged stale."""
    info = getattr(adapter, "SOURCE_INFO", None) or {}
    notes: list[str] = []
    threshold = info.get("stale_after_hours")
    if ledger is not None and threshold and ledger.items_seen > 0 and ledger.newest_item_at is not None:
        age_hours = ((now or datetime.now(timezone.utc)) - ledger.newest_item_at).total_seconds() / 3600
        if age_hours > threshold:
            notes.append(f"STALE: newest item {int(age_hours)}h old (expected under {threshold}h)")
    if len(alerts) >= _FIELD_DRIFT_MIN_ALERTS:
        for field in info.get("expected_fields") or []:
            if all(getattr(a, field, None) in (None, "") for a in alerts):
                notes.append(f"FIELD DRIFT: {field} missing on all {len(alerts)} alerts")
    return notes


def _integrity_row(source_key: str, status: str, ledger, accepted: int, warnings: list[str]) -> dict | None:
    """The row for emergency_alert_source_integrity (migration 0252): what this run's drop
    ledger saw, as queryable data. None when the adapter has no ledger."""
    if ledger is None:
        return None

    def by(prefix: str) -> dict:
        return {k[len(prefix):]: n for k, n in sorted(ledger.counts.items()) if k.startswith(prefix)}

    now = datetime.now(timezone.utc).isoformat()
    return {
        "source_key": source_key, "checked_at": now, "updated_at": now, "status": status,
        "items_seen": ledger.items_seen, "accepted": accepted,
        "excluded": by("excluded_"), "invalid": by("invalid_"), "unmapped": by("unmapped_"),
        "samples": ledger.samples,
        "newest_item_at": ledger.newest_item_at.isoformat() if ledger.newest_item_at else None,
        "warnings": warnings,
    }


def _upsert_integrity(rows: list[dict]) -> None:
    """One batched upsert of the latest per-source integrity rows. Best effort and never
    raises: the table only exists once migration 0252 is applied, and a failed write here
    must never affect the alerts, the heartbeats or the emails."""
    if not rows:
        return
    try:
        _supabase_request(
            "POST", "emergency_alert_source_integrity?on_conflict=source_key", body=rows,
            extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
    except Exception as exc:  # noqa: BLE001 - best-effort observability write (migration 0252 may not be applied yet); must never break ingestion
        log.warning("[emergency-alerts] could not record source integrity (migration 0252 not applied yet?): %s", exc)


def _ledger_verdict(ledger, accepted: int) -> tuple[str | None, str | None]:
    """(failure message, warning text) for one run's drop ledger.

    - items seen, none accepted, some invalid  -> failure: the feed is broken.
    - items seen, none accepted, none invalid  -> (None, None): everything was
      a deliberate exclusion, which is a legitimately quiet feed.
    - more than 20% invalid with some accepted -> warning only (status ok).
    No ledger (adapter has no fetch_with_ledger) -> (None, None)."""
    if ledger is None or ledger.items_seen <= 0:
        return None, None
    invalid = ledger.invalid_total
    if accepted == 0 and invalid > 0:
        if invalid == ledger.items_seen:
            return f"all {ledger.items_seen} items failed structural parsing: {ledger.top_invalid()}", None
        message = (
            f"no items accepted - {invalid} of {ledger.items_seen} failed structural parsing: {ledger.top_invalid()} "
            f"({ledger.excluded_total} deliberately excluded)"
        )
        return message, None
    if accepted > 0 and invalid / ledger.items_seen > _INVALID_WARN_RATIO:
        return None, f"WARNING: {round(100 * invalid / ledger.items_seen)}% invalid ({invalid} of {ledger.items_seen} items)"
    return None, None


def _ok_detail(
    n_rows: int, unknown_count: int, expired: int, emails_sent: int, *,
    coerced: tuple[int, int] | None = None, ledger=None, warning: str | None = None,
) -> str:
    detail = f"{n_rows} alert(s), {unknown_count} unknown severity, {expired} expired"
    if n_rows == 0:
        detail += " (empty feed — earlier alerts held up to 2h before expiring)"
    if emails_sent:
        detail += f", {emails_sent} emergency email(s) sent"
    if warning:
        detail += f" | {warning}"
    if ledger is not None:
        detail += f" | {ledger.summary()}"
    if coerced and any(coerced):
        detail += f" | coerced {sum(coerced)} (alert_type {coerced[0]}, severity {coerced[1]})"
    if len(detail) > _DETAIL_MAX_CHARS:
        detail = detail[: _DETAIL_MAX_CHARS - 1] + "…"
    return detail


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_all(), indent=2, default=str))
