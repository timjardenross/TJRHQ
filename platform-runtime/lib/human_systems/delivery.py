"""Human Systems — Proactive delivery layer (WP7).

Thin adapter that renders a PushMessage and delivers it to the Captain over both
the bot's existing surfaces — **Slack** (`chat_postMessage` DM, the same pattern as
`/health-brief`) and **Telegram** (Bot API `sendMessage`, urllib, no new
dependency). When both are configured a push fans out to both bots; when only one
is, it uses that one; when neither is, it returns the rendered text unsent.

Delivery is privacy-first (Captain DM / configured private chat) and degrades
gracefully, so the same code path powers dry-runs, tests, and the on-demand
`/hs push` preview.

Recipients are configured via env:
  * Slack    — HUMAN_SYSTEMS_CHANNEL (a user id `U…` for a DM, or a channel id);
               token is the bot's existing SLACK_BOT_TOKEN.
  * Telegram — TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (or HUMAN_SYSTEMS_TELEGRAM_CHAT).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

_TELEGRAM_MAX = 4096   # Telegram hard limit per message.


def captain_channel() -> str | None:
    """Configured Captain recipient (Slack user id for DM, or channel id)."""
    return (
        os.environ.get("HUMAN_SYSTEMS_CHANNEL")
        or os.environ.get("CAPTAIN_SLACK_ID")
        or None
    )


def telegram_config() -> tuple[str | None, str | None]:
    """(bot token, chat id) for Telegram delivery, or (None, …) when unconfigured."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("HUMAN_SYSTEMS_TELEGRAM_CHAT")
    return token, chat


def _to_telegram(text: str) -> str:
    """Make Slack mrkdwn readable as Telegram plain text (sent without parse_mode).

    Drops Slack bold markers (`*`); keeps structure, bullets, and emoji. Truncates
    to Telegram's per-message limit."""
    cleaned = (text or "").replace("*", "")
    if len(cleaned) > _TELEGRAM_MAX:
        cleaned = cleaned[: _TELEGRAM_MAX - 1].rstrip() + "…"
    return cleaned


def _send_telegram(text: str, token: str, chat_id: str) -> tuple[bool, str | None]:
    """POST to Telegram sendMessage. Returns (ok, error). Never raises."""
    payload = json.dumps({
        "chat_id": chat_id,
        "text": _to_telegram(text),
        "disable_web_page_preview": True,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        if body.get("ok"):
            return True, None
        return False, str(body.get("description") or "telegram_error")
    except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
        return False, f"HTTPError({exc.code})"
    except Exception as exc:  # pragma: no cover - network dependent
        return False, type(exc).__name__


def get_slack_client():
    """Return a Slack WebClient from SLACK_BOT_TOKEN, or None if unavailable.

    Imported lazily so this module (and its tests) load without slack_sdk.
    """
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        return None
    try:
        from slack_sdk import WebClient  # type: ignore
        return WebClient(token=token)
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("[human-systems.delivery] Slack client unavailable: %s", exc)
        return None


@dataclass
class DeliveryResult:
    delivered: bool
    channel: str | None
    text: str
    kind: str
    severity: str
    dry_run: bool = False
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "delivered": self.delivered,
            "channel": self.channel,
            "kind": self.kind,
            "severity": self.severity,
            "dry_run": self.dry_run,
            "error": self.error,
            "text": self.text,
        }


def deliver(message, *, client=None, channel=None, dry_run: bool = False) -> DeliveryResult:
    """Render and deliver a PushMessage to the Captain over Slack and/or Telegram.

    - dry_run, or no configured surface → returns rendered text, not sent.
    - Otherwise posts to every configured surface and reports the combined outcome.
    Never raises: delivery failure is captured in the result.
    """
    text = message.render()
    channel = channel or captain_channel()
    tg_token, tg_chat = telegram_config()
    telegram_on = bool(tg_token and tg_chat)

    # Slack-only fast paths — preserve the original behaviour exactly when Telegram
    # isn't configured (so existing callers/tests are unaffected).
    if not telegram_on:
        if dry_run or client is None or not channel:
            reason = "dry_run" if dry_run else ("no_client" if client is None else "no_channel")
            return DeliveryResult(
                delivered=False, channel=channel, text=text,
                kind=message.kind, severity=message.severity,
                dry_run=True, error=None if dry_run else reason,
            )
        try:
            client.chat_postMessage(channel=channel, text=text)
            log.info("[human-systems.delivery] delivered kind=%s to=%s", message.kind, channel)
            return DeliveryResult(
                delivered=True, channel=channel, text=text,
                kind=message.kind, severity=message.severity,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            log.error("[human-systems.delivery] delivery failed: %s", exc)
            return DeliveryResult(
                delivered=False, channel=channel, text=text,
                kind=message.kind, severity=message.severity, error=str(exc),
            )

    # Telegram configured → fan out to both bots.
    if dry_run:
        return DeliveryResult(
            delivered=False, channel=f"{channel or '-'}+telegram:{tg_chat}", text=text,
            kind=message.kind, severity=message.severity, dry_run=True, error=None,
        )

    outcomes: list[tuple[str, bool, str | None]] = []
    if client is not None and channel:
        try:
            client.chat_postMessage(channel=channel, text=text)
            outcomes.append(("slack", True, None))
        except Exception as exc:  # pragma: no cover - network dependent
            outcomes.append(("slack", False, str(exc)))
    tg_ok, tg_err = _send_telegram(text, tg_token, tg_chat)
    outcomes.append(("telegram", tg_ok, tg_err))

    delivered = any(ok for _, ok, _ in outcomes)
    sent_to = "+".join(name for name, ok, _ in outcomes if ok) or None
    errors = "; ".join(f"{name}:{err}" for name, ok, err in outcomes if not ok and err)
    log.info("[human-systems.delivery] kind=%s delivered_to=%s", message.kind, sent_to or "none")
    return DeliveryResult(
        delivered=delivered, channel=sent_to or channel, text=text,
        kind=message.kind, severity=message.severity,
        error=None if delivered else (errors or None),
    )
