"""Telegram sender for incident alerts: the EXISTING XO sender, nothing new.

Delivery goes through ``core.platform.notification_service.notify`` (Transport.TELEGRAM), the same path ``captains_brief._send_telegram``
uses for the morning/midday/EOD briefs. Bot token and default chat come from the env the ``intelligence-scheduler`` unit already has
(``run-with-infisical-bot.sh xo`` -> TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_IDS / TELEGRAM_CHAT_ID). No new bot, no new secret.

Destination (``INCIDENT_ALERT_DESTINATION``): the literal ``xo`` means "the XO bot's default chat, resolved exactly as the brief resolves it".
Any other value is used as an explicit chat id (not recommended: it duplicates a value Infisical already holds).

No retry inside the notification service (max_retries=0): a retry after an ambiguous timeout could deliver an alert twice. A failed send
returns False and the dispatcher releases the claim so the NEXT pass retries once, from a known state.
"""
from __future__ import annotations

import html
import logging

log = logging.getLogger(__name__)

XO_DEFAULT = "xo"
TEST_HEADLINE = "[TEST] Alert path check — no incident"
_HEADERS = {"alert": "🚨 <b>INCIDENT ALERT</b>", "restoration": "✅ <b>INCIDENT RESTORED</b>", "test": "🧪 <b>[TEST] ALERT PATH CHECK</b>"}


def format_message(payload: dict) -> str:
    """Telegram HTML. Visually distinct from a brief: a bold banner line first, then the dispatcher's facts-only text (escaped)."""
    kind = payload.get("kind", "alert")
    if kind == "test":
        return "\n".join([_HEADERS["test"], html.escape(TEST_HEADLINE), "No incident exists. This confirms the alert path only. No action needed."])
    body = str(payload.get("text", ""))
    lines = body.split("\n")
    if lines and lines[0].split(":", 1)[0] in ("ALERT", "RESTORED"):
        lines[0] = "<b>" + html.escape(lines[0].split(":", 1)[1].strip()) + "</b>"
        lines[1:] = [html.escape(x) for x in lines[1:]]
    else:
        lines = [html.escape(x) for x in lines]
    return "\n".join([_HEADERS.get(kind, _HEADERS["alert"])] + lines)


def send(payload: dict, destination: str) -> bool:
    """Signature required by ``alert_dispatcher.process(sender=...)``: returns True only if Telegram accepted the message."""
    from core.platform.notification_service import Transport, notify
    chat_id = None if destination.strip().lower() == XO_DEFAULT else destination.strip()
    result = notify(format_message(payload), template="raw", transport=Transport.TELEGRAM, chat_id=chat_id, max_retries=0)
    if not result.ok:
        log.warning("[incident-alert] telegram send failed: %s", result.error)
    return bool(result.ok)
