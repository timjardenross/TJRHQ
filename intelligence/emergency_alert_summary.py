"""Emergency Alert Hub — hourly LLM summary email (migration 0177).

Captain-directed 2026-08-27: "post the event cycle running each hour,
produce an email summary using an LLM". Checks hourly (scheduled from
intelligence/scheduler.py); only calls the LLM and sends an email when the
active-alert set actually changed since the last send — a cheap DB diff
(hash of id+severity+status per active alert) covers the common "nothing
changed" hour without spending an LLM call or an email.

Captain-directed 2026-08-29: still repeated hourly even after the 08-27
unknown-severity fix, because Advice-tier alerts (routine bushfire/flood
churn) flip status hourly too, so the fingerprint kept changing. Now: any
alert at watch_and_act/emergency_warning tier still emails immediately on
change (real urgency); if the whole active set is Advice/unknown only, hold
and send at most once per day (~8am AEST, _DIGEST_HOUR_UTC) instead.

Reuses two already-live primitives rather than building new ones:
  - core/llm/provider_chain.py (Gemini -> Mistral fallback), the same
    provider chain intelligence/brief/daily_digest.py and
    core/platform/infra_narrative.py already use for narrative synthesis.
  - core/notifications/resend_email.py, the same Resend wrapper
    intelligence/emergency_alerts.py uses for Emergency Warning alerts.

Never raises — a summary failure must never break the alert ingestion job
it runs alongside.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
import urllib.request
from html import escape as _esc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))
import alert_silences
from heartbeat import _KEY, _URL, record_heartbeat, supabase_get

from core.llm.provider_chain import call_gemini, call_mistral
from core.notifications.resend_email import send_email

log = logging.getLogger("emergency-alert-summary")

_DOMAIN_KEY = "emergency_alert_hourly_summary"
_EMAIL_TO = os.environ.get("EMERGENCY_ALERT_EMAIL_TO", "timjardenross1986@gmail.com")
_EMAIL_CC = os.environ.get("EMERGENCY_ALERT_EMAIL_CC") or None
_URGENT_TIERS = {"emergency_warning", "watch_and_act"}
_DIGEST_HOUR_UTC = 22  # ~8am AEST

_SYSTEM_PROMPT = (
    "You are the Emergency Alert Hub's daily digest writer for a business "
    "continuity team that wants situational awareness across Australia's "
    "emergency alerts (bushfire, flood, storm, cyclone) without reading each "
    "one individually. Urgent alerts have already been emailed to the team "
    "one by one; this digest is the daily overview. Write a short email body: 2-4 short paragraphs, plain "
    "language, group by geography/theme where it makes sense, lead with "
    "anything genuinely urgent (Watch and Act / Emergency Warning tier) if "
    "present, otherwise state plainly that nothing is above Advice level. "
    "Never invent facts not present in the data. End with one line noting "
    "total active alert count."
)


def _fingerprint(alerts: list[dict]) -> str:
    """Captain-flagged 2026-08-27: hourly emails were "primarily the same
    update" — reviewed the logs (every hour fired 'changed: True') against
    live data and found why: severity='unknown' alerts (WA/SA CAD-tier
    feeds with no warning-level data — see wa_dfes.py/sa_cfs.py) are ~65%
    of the active set and churn constantly (one flips active/inactive most
    hours) even when nothing genuinely newsworthy happened. Any single
    change anywhere in the full set was enough to trigger a full re-send.

    Fingerprint now excludes severity='unknown' alerts — real
    Advice/Watch and Act/Emergency Warning tier changes still trigger a
    fresh summary immediately; unknown-tier churn no longer does. Trade-
    off, deliberate: a brand-new unknown-severity incident (e.g. a fresh
    WA bushfire with no matching warning yet) won't trigger its own email
    on that basis alone — it's still visible on the live workbench, and
    still included in the email body whenever an advice+ change does fire
    one (see _build_prompt, which uses the unfiltered alert list)."""
    material = [a for a in alerts if a["severity"] != "unknown"]
    parts = sorted(f"{a['id']}:{a['severity']}:{a['status']}" for a in material)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _get_state() -> dict:
    rows = supabase_get("emergency_alert_summary_state?id=eq.1&select=*")
    return rows[0] if rows else {"last_fingerprint": None, "last_sent_at": None}


def _set_state(fingerprint: str, sent_at: str) -> None:
    if not _URL or not _KEY:
        return
    body = json.dumps({"id": 1, "last_fingerprint": fingerprint, "last_sent_at": sent_at}).encode("utf-8")
    req = urllib.request.Request(
        f"{_URL.rstrip('/')}/rest/v1/emergency_alert_summary_state?on_conflict=id",
        data=body,
        method="POST",
        headers={
            "apikey": _KEY,
            "Authorization": f"Bearer {_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    with urllib.request.urlopen(req, timeout=15):  # nosec B310 - url is built from SUPABASE_URL env var (_URL), always https - reviewed 2026-09-12
        return


def _build_prompt(alerts: list[dict]) -> str:
    lines = []
    for a in alerts:
        desc = (a.get("description") or "")[:400]
        line = (
            f"- [{a['jurisdiction']}] ({a['alert_type']}, severity={a['severity']}) {a['headline']}"
        )
        if a.get("location"):
            line += f" | location: {a['location']}"
        if a.get("issued_at"):
            line += f" | issued: {a['issued_at']}"
        if desc:
            line += f"\n  detail: {desc}"
        lines.append(line)
    return f"Current active alerts ({len(alerts)} total):\n\n" + "\n".join(lines)


def _verbatim_urgent_section(alerts: list[dict]) -> str:
    """HQ V1 Integration QA §7/§9: the hourly digest's LLM prose is asked
    not to invent facts, but is not required to preserve official
    headline/jurisdiction wording verbatim — a real paraphrasing risk for
    the safety-critical tiers specifically. Appends the raw, unedited
    official fields for every watch_and_act/emergency_warning alert
    regardless of what the summary prose says, so official wording always
    survives even if the LLM's paraphrase doesn't. No-op (empty string)
    when nothing urgent is active — the common case, so this never adds
    noise to a routine Advice-only digest."""
    urgent = [a for a in alerts if a["severity"] in _URGENT_TIERS]
    if not urgent:
        return ""
    rows = "".join(
        f"<li><strong>[{a['severity'].upper()}] {a['jurisdiction']}</strong> — {a['headline']}"
        + (f" ({a['location']})" if a.get("location") else "")
        + "</li>"
        for a in urgent
    )
    return f"<hr><p><strong>Official alert wording (verbatim):</strong></p><ul>{rows}</ul>"


_DROPPED_SAMPLES_PER_REASON = 2


def _dropped_section() -> str:
    """Feed health and what the hub is deliberately dropping, from the latest per-source drop
    ledger (emergency_alert_source_integrity, migration 0252). Verbatim counts and public feed
    titles, no LLM: so a reviewer can SEE what is excluded (e.g. WA Smoke Alerts, a new BOM
    product) instead of it only existing as a count inside a heartbeat. Empty string when
    the table is unavailable or nothing is noteworthy; never raises."""
    try:
        rows = supabase_get(
            "emergency_alert_source_integrity?order=source_key.asc"
            "&select=source_key,status,items_seen,accepted,excluded,invalid,unmapped,samples,warnings"
        )
    except Exception as exc:  # noqa: BLE001 - optional digest section; a read failure must never block the digest
        log.warning("[emergency-alert-summary] could not read source integrity (migration 0252 not applied?): %s", exc)
        return ""
    items = []
    for row in rows or []:
        excluded, invalid, unmapped = row.get("excluded") or {}, row.get("invalid") or {}, row.get("unmapped") or {}
        warnings = row.get("warnings") or []
        if not (sum(excluded.values()) or sum(invalid.values()) or unmapped or warnings or row.get("status") == "failed"):
            continue
        samples = row.get("samples") or {}
        parts = []
        for label, counts, prefix in (("excluded", excluded, "excluded_"), ("invalid", invalid, "invalid_")):
            bits = []
            for reason, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                shown = samples.get(f"{prefix}{reason}", [])[:_DROPPED_SAMPLES_PER_REASON]
                example = " (e.g. " + "; ".join(f"“{_esc(s)}”" for s in shown) + ")" if shown else ""
                bits.append(f"{_esc(reason)} {n}{example}")
            if bits:
                parts.append(f"{label}: " + ", ".join(bits))
        if unmapped:
            parts.append("unrecognised: " + ", ".join(f"{_esc(k)} {v}" for k, v in sorted(unmapped.items(), key=lambda kv: (-kv[1], kv[0]))[:3]))
        flags = "".join(f" <strong>{_esc(str(w))}</strong>" for w in warnings)
        failed = " <strong>FAILED</strong>" if row.get("status") == "failed" else ""
        items.append(
            f"<li><strong>{_esc(str(row['source_key']))}</strong>{failed}: saw {row.get('items_seen', 0)}, kept {row.get('accepted', 0)}"
            + ("; " + "; ".join(parts) if parts else "") + flags + "</li>"
        )
    if not items:
        return ""
    return (
        "<hr><p><strong>Feed health and what the hub is dropping (latest run per source):</strong></p>"
        "<p>Counts are deliberate exclusions, not errors. Anything flagged STALE, FIELD DRIFT or FAILED needs a look.</p>"
        f"<ul>{''.join(items)}</ul>"
    )


def _generate_summary(alerts: list[dict]) -> tuple[str, str] | None:
    prompt = _build_prompt(alerts)
    try:
        return call_gemini(_SYSTEM_PROMPT, prompt, api_key=os.environ.get("GEMINI_API_KEY", "")).text, "gemini"
    except Exception as exc:  # noqa: BLE001 - per-provider attempt inside a fallback chain (Gemini -> Mistral) — one provider failing must not abort the chain; already logged
        log.warning("[emergency-alert-summary] Gemini failed, falling back to Mistral: %s", exc)
    try:
        return call_mistral(_SYSTEM_PROMPT, prompt, api_key=os.environ.get("MISTRAL_API_KEY", "")).text, "mistral"
    except Exception as exc:  # noqa: BLE001 - final provider in the fallback chain; already logged, caller treats None as 'summary unavailable'
        log.warning("[emergency-alert-summary] Mistral also failed: %s", exc)
        return None


def _exclude_silenced(alerts: list[dict]) -> list[dict]:
    """Drops any alert currently covered by an active alert_silences rule
    (migration 0205) before this hourly digest does anything else with the
    active set — fingerprinting, the urgent-tier check, the LLM prompt, and
    the verbatim official-wording section all only ever see what's left.
    A planned hazard-reduction burn silenced for a jurisdiction should stop
    showing up in the hourly email the same way it stops triggering its own
    per-alert emergency-warning email (emergency_alerts.py's
    _send_emergency_warning_emails) — otherwise "mute this" would still
    leave it narrated in the digest an hour later.

    Never raises: a silence-lookup failure degrades to "nothing silenced"
    rather than blocking a real hourly summary — same posture as
    emergency_alerts.py's own silence check."""
    try:
        active_silences = alert_silences.list_active_silences()
    except Exception as exc:  # noqa: BLE001 - a silence-lookup failure must never block the hourly digest; degrade to "no active silences"
        log.warning("[emergency-alert-summary] failed to read active silences (proceeding as if none): %s", exc)
        return alerts
    return [a for a in alerts if alert_silences.check_silence(a, active_silences) is None]


def run() -> dict:
    t0 = time.monotonic()
    try:
        alerts = supabase_get(
            "alerts?is_active=eq.true&order=jurisdiction.asc,alert_type.asc"
            "&select=id,jurisdiction,alert_type,severity,status,headline,location,description,issued_at,source_key"
        )
    except Exception as exc:  # noqa: BLE001 - top-level job boundary — already logged + heartbeat-recorded, surfaces error in the returned dict
        record_heartbeat(_DOMAIN_KEY, status="failed", error_message=str(exc)[:500])
        return {"error": str(exc)}

    alerts = _exclude_silenced(alerts)

    fingerprint = _fingerprint(alerts)
    state = _get_state()

    # One digest a day (~8am AEST), sent even when nothing changed: urgent alerts
    # are emailed individually the moment they appear (intelligence/
    # emergency_alerts.py), so the digest no longer fires on every urgent change.
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    last_sent_at = state.get("last_sent_at")
    already_sent_today = bool(last_sent_at) and last_sent_at[:10] == now.date().isoformat()
    if now.hour < _DIGEST_HOUR_UTC or already_sent_today:
        record_heartbeat(
            _DOMAIN_KEY,
            status="ok",
            detail=f"{len(alerts)} active alert(s) - holding for the daily digest, no email sent",
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
        return {"changed": fingerprint != state.get("last_fingerprint"), "count": len(alerts), "emailed": False, "held_for_digest": True}

    result = _generate_summary(alerts)
    if result is None:
        record_heartbeat(_DOMAIN_KEY, status="failed", error_message="LLM synthesis failed (Gemini + Mistral both failed)")
        return {"changed": True, "count": len(alerts), "emailed": False, "error": "llm_failed"}

    summary_text, provider = result
    subject = f"[DIGEST] Emergency Alert Hub - daily overview ({len(alerts)} active)"
    html = '<pre style="font-family:monospace;white-space:pre-wrap">Notice: DIGEST\nActive-Alerts: ' + str(len(alerts)) + "</pre>"
    html += "<p>" + summary_text.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    html += _verbatim_urgent_section(alerts)
    html += _dropped_section()

    sent = send_email(to=_EMAIL_TO, subject=subject, html=html, cc=_EMAIL_CC) if _EMAIL_CC else send_email(to=_EMAIL_TO, subject=subject, html=html)
    now_iso = None
    if sent:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            _set_state(fingerprint, now_iso)
        except Exception as exc:  # noqa: BLE001 - best-effort dedupe-state persistence, already logged as non-blocking (email already sent by this point)
            log.warning("[emergency-alert-summary] sent email but failed to persist state — may re-send next hour: %s", exc)

    detail = f"{len(alerts)} active alert(s), summary via {provider}, email {'sent' if sent else 'FAILED'}"
    record_heartbeat(_DOMAIN_KEY, status="ok" if sent else "failed", detail=detail if sent else None, error_message=None if sent else "email send failed", latency_ms=int((time.monotonic() - t0) * 1000))
    return {"changed": True, "count": len(alerts), "emailed": sent, "provider": provider}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run(), indent=2, default=str))
