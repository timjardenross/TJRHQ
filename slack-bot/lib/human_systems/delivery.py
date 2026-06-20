"""Human Systems — Proactive delivery layer (WP7).

Thin adapter that renders a PushMessage and delivers it to the Captain over the
existing Slack notification surface, reusing the same `chat_postMessage` DM
pattern as `/health-brief` (commands/health_synthesis.py). No new transport is
introduced.

Delivery is privacy-first (Captain DM / configured private channel) and degrades
gracefully: with no Slack client or no configured recipient it returns the
rendered text without sending, so the same code path powers dry-runs, tests, and
the on-demand `/hs push` preview.

Recipient is configured via env HUMAN_SYSTEMS_CHANNEL (a Slack user id `U…` for a
DM, or a private channel id). Token is the bot's existing SLACK_BOT_TOKEN.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)


def captain_channel() -> str | None:
    """Configured Captain recipient (Slack user id for DM, or channel id)."""
    return (
        os.environ.get("HUMAN_SYSTEMS_CHANNEL")
        or os.environ.get("CAPTAIN_SLACK_ID")
        or None
    )


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
    """Render and deliver a PushMessage to the Captain.

    - dry_run, or a missing client/channel → returns rendered text, not sent.
    - Otherwise posts via chat_postMessage and reports the outcome.
    Never raises: delivery failure is captured in the result.
    """
    text = message.render()
    channel = channel or captain_channel()

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
