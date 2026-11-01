"""Human Systems — Proactive delivery layer (WP7).

Thin adapter that renders a PushMessage and delivers it to the Captain over
Telegram (Bot API `sendMessage`, urllib, no new dependency).

2026-09-08: Slack retired as a transport (Captain direction — Slack was
disabled). This module previously fanned a push out to both Slack
(`chat_postMessage` DM) and Telegram when both were configured; Telegram is
now the only surface.

Delivery is privacy-first (configured private chat) and degrades
gracefully, so the same code path powers dry-runs, tests, and the on-demand
`/hs push` preview.

Recipient is configured via env: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (or
HUMAN_SYSTEMS_TELEGRAM_CHAT).
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


def telegram_config() -> tuple[str | None, str | None]:
    """(bot token, chat id) for Telegram delivery, or (None, …) when unconfigured."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("HUMAN_SYSTEMS_TELEGRAM_CHAT")
    return token, chat


def _to_telegram(text: str) -> str:
    """Strip legacy mrkdwn-style bold markers (`*`) inherited from message
    templates that predate Slack's retirement; keeps structure, bullets, and
    emoji. Truncates to Telegram's per-message limit. Sent without
    parse_mode, so no HTML/Markdown escaping is needed here."""
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
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310 - url is the fixed api.telegram.org sendMessage endpoint with only the bot token (env var) interpolated, not user input - reviewed 2026-09-12
            body = json.loads(response.read().decode("utf-8"))
        if body.get("ok"):
            return True, None
        return False, str(body.get("description") or "telegram_error")
    except urllib.error.HTTPError as exc:  # pragma: no cover - network dependent
        return False, f"HTTPError({exc.code})"
    except Exception as exc:  # noqa: BLE001 - documented "never raises" network contract, error type returned to caller - pragma: no cover - network dependent
        return False, type(exc).__name__


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


def deliver(message, *, dry_run: bool = False) -> DeliveryResult:
    """Render and deliver a PushMessage to the Captain over Telegram.

    - dry_run, or Telegram unconfigured → returns rendered text, not sent.
    - Otherwise posts to Telegram and reports the outcome.
    Never raises: delivery failure is captured in the result.
    """
    text = message.render()
    tg_token, tg_chat = telegram_config()
    telegram_on = bool(tg_token and tg_chat)

    if dry_run or not telegram_on:
        reason = "dry_run" if dry_run else "no_telegram_config"
        return DeliveryResult(
            delivered=False, channel=f"telegram:{tg_chat}" if telegram_on else None, text=text,
            kind=message.kind, severity=message.severity,
            dry_run=True, error=None if dry_run else reason,
        )

    tg_ok, tg_err = _send_telegram(text, tg_token, tg_chat)
    log.info("[human-systems.delivery] kind=%s delivered=%s", message.kind, tg_ok)
    return DeliveryResult(
        delivered=tg_ok, channel="telegram" if tg_ok else None, text=text,
        kind=message.kind, severity=message.severity,
        error=None if tg_ok else tg_err,
    )
