"""§5.4 escalation to a human — closes the launch blocker the source doc
called "the largest unmitigated risk in the product." Crisis triggers
(§5.4a language, §5.4b non-text) now alert the Captain, via XO's own bot
identity and chat — not by merging this bot into XO, just by using
XO's Bot API credentials to send one message. Deliberately NOT routed
through XO's own /app.py process — a raw HTTP call to Telegram's
sendMessage endpoint needs nothing from XO's running state, so REVS
doesn't need XO to be up, and XO's process never touches REVS user data.

Design choice worth flagging explicitly: the alert includes the
triggering message's actual text (truncated), not just a "something
happened" ping. The source doc's §5.7 storage-time-screening caution is
about not replaying a user's own words back AT that user later — a
different concern from giving the designated human responder enough to
actually act. Withholding the text would make the escalation close to
useless for deciding whether/how to follow up. Revisit this call if it
turns out to be the wrong one.
"""

from __future__ import annotations

import logging

import httpx

import config

log = logging.getLogger("revs-bot.escalate")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


async def notify_captain(
    *,
    user_id: int,
    first_name: str | None,
    trigger_type: str,
    locale: str | None,
    triggered_text: str | None = None,
) -> bool:
    """Best-effort — a failure here must never block or delay the user's
    own crisis-response message (that send always happens first, this is
    fire-and-forget after). Returns False (and logs) on any failure rather
    than raising, so a bad XO token/chat_id can't take down the crisis
    path itself."""
    if not config.XO_ESCALATION_BOT_TOKEN or not config.XO_ESCALATION_CHAT_ID:
        log.error(
            "[escalate] XO_ESCALATION_BOT_TOKEN/CHAT_ID not available "
            "(telegram-bots/xo/.env missing or incomplete) — crisis "
            "trigger for user %s was NOT escalated to a human", user_id,
        )
        return False

    lines = [
        "REVS crisis trigger",
        f"User: {first_name or 'unknown'} ({user_id})",
        f"Type: {trigger_type} · Locale: {locale or 'unset'}",
    ]
    if triggered_text:
        snippet = triggered_text.strip().replace("\n", " ")[:300]
        lines.append(f'Message: "{snippet}"')
    text = "\n".join(lines)

    url = _TELEGRAM_API.format(token=config.XO_ESCALATION_BOT_TOKEN)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"chat_id": config.XO_ESCALATION_CHAT_ID, "text": text})
        if resp.status_code != 200:
            log.error("[escalate] Telegram API returned %s for user %s: %s", resp.status_code, user_id, resp.text[:300])
            return False
        return True
    except Exception:
        log.exception("[escalate] failed to notify Captain for user %s", user_id)
        return False
