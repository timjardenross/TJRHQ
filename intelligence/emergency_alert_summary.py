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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "platform"))
from heartbeat import _URL, _KEY, record_heartbeat, supabase_get  # noqa: E402

from core.llm.provider_chain import call_gemini, call_mistral
from core.notifications.resend_email import send_email

log = logging.getLogger("emergency-alert-summary")

_DOMAIN_KEY = "emergency_alert_hourly_summary"
_EMAIL_TO = os.environ.get("EMERGENCY_ALERT_EMAIL_TO", "timjardenross1986@gmail.com")
_URGENT_TIERS = {"emergency_warning", "watch_and_act"}
_DIGEST_HOUR_UTC = 22  # ~8am AEST

_SYSTEM_PROMPT = (
    "You are the Emergency Alert Hub's hourly summarizer for Captain TJR, a "
    "single reader who wants situational awareness across Australia's Tier 1 "
    "emergency alerts (bushfire, flood, storm, cyclone) without reading each "
    "one individually. Write a short email body: 2-4 short paragraphs, plain "
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
    with urllib.request.urlopen(req, timeout=15):
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


def _generate_summary(alerts: list[dict]) -> tuple[str, str] | None:
    prompt = _build_prompt(alerts)
    try:
        return call_gemini(_SYSTEM_PROMPT, prompt, api_key=os.environ.get("GEMINI_API_KEY", "")), "gemini"
    except Exception as exc:
        log.warning("[emergency-alert-summary] Gemini failed, falling back to Mistral: %s", exc)
    try:
        return call_mistral(_SYSTEM_PROMPT, prompt, api_key=os.environ.get("MISTRAL_API_KEY", "")), "mistral"
    except Exception as exc:
        log.warning("[emergency-alert-summary] Mistral also failed: %s", exc)
        return None


def run() -> dict:
    t0 = time.monotonic()
    try:
        alerts = supabase_get(
            "alerts?is_active=eq.true&order=jurisdiction.asc,alert_type.asc"
            "&select=id,jurisdiction,alert_type,severity,status,headline,location,description,issued_at"
        )
    except Exception as exc:
        record_heartbeat(_DOMAIN_KEY, status="failed", error_message=str(exc)[:500])
        return {"error": str(exc)}

    fingerprint = _fingerprint(alerts)
    state = _get_state()

    if fingerprint == state.get("last_fingerprint"):
        record_heartbeat(_DOMAIN_KEY, status="ok", detail=f"unchanged, {len(alerts)} active alert(s), no email sent", latency_ms=int((time.monotonic() - t0) * 1000))
        return {"changed": False, "count": len(alerts), "emailed": False}

    urgent = any(a["severity"] in _URGENT_TIERS for a in alerts)
    if not urgent:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        last_sent_at = state.get("last_sent_at")
        already_sent_today = bool(last_sent_at) and last_sent_at[:10] == now.date().isoformat()
        if now.hour < _DIGEST_HOUR_UTC or already_sent_today:
            record_heartbeat(
                _DOMAIN_KEY,
                status="ok",
                detail=f"Advice/unclassified only ({len(alerts)} active) — holding for daily digest, no email sent",
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            return {"changed": True, "count": len(alerts), "emailed": False, "held_for_digest": True}

    result = _generate_summary(alerts)
    if result is None:
        record_heartbeat(_DOMAIN_KEY, status="failed", error_message="LLM synthesis failed (Gemini + Mistral both failed)")
        return {"changed": True, "count": len(alerts), "emailed": False, "error": "llm_failed"}

    summary_text, provider = result
    subject = f"Emergency Alert Hub — hourly summary ({len(alerts)} active)"
    html = "<p>" + summary_text.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    html += _verbatim_urgent_section(alerts)

    sent = send_email(to=_EMAIL_TO, subject=subject, html=html)
    now_iso = None
    if sent:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            _set_state(fingerprint, now_iso)
        except Exception as exc:
            log.warning("[emergency-alert-summary] sent email but failed to persist state — may re-send next hour: %s", exc)

    detail = f"{len(alerts)} active alert(s), summary via {provider}, email {'sent' if sent else 'FAILED'}"
    record_heartbeat(_DOMAIN_KEY, status="ok" if sent else "failed", detail=detail if sent else None, error_message=None if sent else "email send failed", latency_ms=int((time.monotonic() - t0) * 1000))
    return {"changed": True, "count": len(alerts), "emailed": sent, "provider": provider}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run(), indent=2, default=str))
