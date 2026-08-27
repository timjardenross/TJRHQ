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

from core.notifications.resend_email import send_email

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


def notify_published(brief: dict) -> bool:
    """`brief` is the intelligence_briefs row (pre- or post-update — only
    fields already present before the publish transition are used:
    period_end, overall_risk, executive_snapshot, bottom_line). Returns
    True if the email was sent; never raises."""
    try:
        period_end = brief.get("period_end") or "today"
        risk = brief.get("overall_risk") or "unrated"
        snapshot = brief.get("executive_snapshot") or brief.get("bottom_line") or ""

        subject = f"📋 Captain's Brief Ready — {period_end}"
        html = (
            f"<p>The Captain's Brief for <strong>{period_end}</strong> has been published "
            f"(risk: {risk}).</p>"
            + (f"<p>{snapshot}</p>" if snapshot else "")
            + f'<p><a href="{_BRIEFS_PAGE_URL}">Read it on the Briefs page →</a></p>'
        )
        return send_email(to=_BRIEF_EMAIL_TO, subject=subject, html=html, from_addr=_BRIEF_EMAIL_FROM)
    except Exception as exc:
        log.warning("[brief-published-notifier] failed to send: %s", exc)
        return False
