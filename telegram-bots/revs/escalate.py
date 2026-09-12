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

import datetime as dt
import html
import logging

import httpx

import config

log = logging.getLogger("revs-bot.escalate")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

_TRIGGER_LABELS = {
    "language": "flagged from something they typed",
    "nontext": "flagged from check-in pattern — no message text involved",
}

# parse_mode="HTML" — chosen over Markdown/MarkdownV2 specifically because
# triggered_text/first_name/detail are raw user input. MarkdownV2 requires
# escaping ~18 special characters and a single missed one causes Telegram
# to reject the whole request (silently dropping the alert); HTML only
# needs & < > escaped, which html.escape() does correctly and completely.
# Every user-controlled value below goes through html.escape() before
# interpolation — do not add a new field here without doing the same.
_RESOURCE_NOTE = {
    "language": "Bot already sent this user {locale} crisis resources and will check back with them in 24h.",
    "nontext": "No text from the user to act on — this fired from their check-in pattern alone. Bot sent a light-touch resources message.",
}


async def notify_captain(
    *,
    user_id: int,
    first_name: str | None,
    trigger_type: str,  # "language" or "nontext"
    locale: str | None,
    triggered_text: str | None = None,
    detail: str | None = None,
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

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    kind_label = _TRIGGER_LABELS.get(trigger_type, trigger_type)
    safe_name = html.escape(first_name or "unknown")
    safe_locale = html.escape(locale or "unset")
    safe_detail = html.escape(detail) if detail else None

    lines = [
        "\U0001F6A8 <b>REVS crisis alert</b>",
        "",
        f"<b>Who:</b> {safe_name} (id {user_id})",
        f"<b>When:</b> {now}   <b>Locale:</b> {safe_locale}",
        f"<b>Why:</b> {kind_label}",
    ]
    if safe_detail:
        lines.append(f"<b>Detail:</b> {safe_detail}")
    if triggered_text:
        snippet = html.escape(triggered_text.strip().replace("\n", " ")[:300])
        lines.append("")
        lines.append(f'<b>Message:</b>\n<i>"{snippet}"</i>')
    lines.append("")
    note = _RESOURCE_NOTE.get(trigger_type, "").format(locale=safe_locale)
    lines.append(f"<i>{note}</i>")
    text = "\n".join(l for l in lines if l is not None)

    url = _TELEGRAM_API.format(token=config.XO_ESCALATION_BOT_TOKEN)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={"chat_id": config.XO_ESCALATION_CHAT_ID, "text": text, "parse_mode": "HTML"},
            )
        if resp.status_code != 200:
            log.error("[escalate] Telegram API returned %s for user %s: %s", resp.status_code, user_id, resp.text[:300])
            return False
        return True
    except Exception:
        log.exception("[escalate] failed to notify Captain for user %s", user_id)
        return False
