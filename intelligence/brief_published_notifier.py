"""Email notification when a Captain's Brief is published (Captain: "trigger
once a brief is finalised for the day and ready to be read... link direct
to the briefs page").

Hooked directly into intelligence/workflow/service.py's publish_brief() —
that function is the single choke point every publish path goes through
(the workflow API, tests), and its own approval_status state machine
(_require_brief_transition) already guarantees QA_PASSED -> PUBLISHED
fires exactly once per brief, so no separate dedupe state is needed here
(unlike the hourly Emergency Alert Hub summary, which polls and needs its
own fingerprint).

Reuses core/notifications/resend_email.py (same Resend wrapper the
Emergency Alert Hub uses) — never raises, a notification failure must
never break an actual brief publish.
"""

from __future__ import annotations

import logging
import os
from html import escape as html_escape

from core.notifications.resend_email import send_email
from intelligence.reporting_time import flag_enabled

log = logging.getLogger("brief-published-notifier")

_BRIEF_EMAIL_TO = os.environ.get("BRIEF_PUBLISHED_EMAIL_TO", "timjardenross@outlook.com")
# Own sender display name (Captain: "use a different Send Name for that
# email") — distinct from resend_email.py's "Emergency Alert Hub" default,
# same verified tjrmindbody.com address underneath.
_BRIEF_EMAIL_FROM = os.environ.get("BRIEF_PUBLISHED_EMAIL_FROM", "Captain's Brief <alerts@tjrmindbody.com>")
# Captain-corrected 2026-08-27, second pass: the LCARS Portal the Captain
# actually reads day-to-day is the Vercel deployment
# (usstjros.vercel.app), not the VM's own Caddy-fronted address
# (109.123.227.196:8444) — both are real/reachable, this is the one to
# link from email. tjrmindbody.com (a separate public marketing site) was
# the first wrong guess; the VM address was the second.
_BRIEFS_PAGE_URL = os.environ.get("BRIEFS_PAGE_URL", "https://usstjros.vercel.app/briefs")


def _production_status_html(brief: dict) -> str:
    """BRIEF_STATUS_V1 (default off): one line stating the brief's production status, read from the stored record. Production status
    is about content and collection only; it is never derived from, and never changes with, whether this e-mail is sent. Empty when the
    flag is off or no record is stored, so the message is unchanged."""
    try:
        from intelligence.brief import ori_status
        if not ori_status.enabled():
            return ""
        rec = ori_status.from_row(brief)
        if not rec or rec.get("status") in (None, "NORMAL"):
            return ""
        reasons = ", ".join(str(r) for r in (rec.get("reasons") or [])[:4])
        return f"<p><em>Production status: {html_escape(str(rec['status']))}" + (f" ({html_escape(reasons)})" if reasons else "") + ".</em></p>"
    except Exception as exc:  # noqa: BLE001 - additive line; never break the notification
        log.debug("[brief-published-notifier] status line unavailable: %s", exc)
        return ""


def notify_published(brief: dict) -> bool:
    """`brief` is the intelligence_briefs row (pre- or post-update — only
    fields already present before the publish transition are used:
    period_end, overall_risk, executive_snapshot, bottom_line). Returns
    True if the email was sent; never raises."""
    try:
        period_end = brief.get("period_end") or "today"
        if flag_enabled() and brief.get("morning_cycle_id"):
            # morning_cycle_id is the Melbourne date; period_end on rows written before the fix is the UTC date (a day behind).
            period_end = brief["morning_cycle_id"]
        risk = brief.get("overall_risk") or "unrated"
        snapshot = brief.get("executive_snapshot") or brief.get("bottom_line") or ""
        try:                                                        # BRIEF_CLAIM_GATE_V1=enforce: only governed stored text is e-mailed
            from intelligence.brief import display_governance as dg
            if dg.enforcing():
                snapshot = dg.governed_text(brief, "executive_snapshot", "bottom_line")
        except Exception:  # noqa: BLE001 - cannot establish governance: send no generated text
            snapshot = ""

        period_label = " ".join(str(period_end).split())[:40]
        subject = f"📋 Captain's Brief Ready — {period_label}"
        # Everything interpolated into the HTML is escaped (generated text can carry markup); line breaks are kept as <br>.
        snapshot_html = html_escape(str(snapshot)).replace("\r\n", "\n").replace("\n", "<br>\n") if snapshot else ""
        html = (
            f"<p>The Captain's Brief for <strong>{html_escape(str(period_end))}</strong> has been published "
            f"(risk: {html_escape(str(risk))}).</p>"
            + (f"<p>{snapshot_html}</p>" if snapshot_html else "")
            + _production_status_html(brief)
            + f'<p><a href="{_BRIEFS_PAGE_URL}">Read it on the Briefs page →</a></p>'
        )
        return send_email(to=_BRIEF_EMAIL_TO, subject=subject, html=html, from_addr=_BRIEF_EMAIL_FROM)
    except Exception as exc:  # noqa: BLE001 - best-effort email send, already logged; caller sees False and treats it as non-blocking
        log.warning("[brief-published-notifier] failed to send: %s", exc)
        return False
