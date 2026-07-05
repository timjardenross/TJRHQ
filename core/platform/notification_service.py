"""Notification Service (SUOC Wave 2 Platform Service, MSN-0210F Part 2).

Generalises core/coordination/command_bus.py's private `_telegram`/`_slack`
senders into a proper service: severity-as-real-data (not ad-hoc strings),
a small message-template registry, delivery-status tracking, retry with
backoff, and an in-process call log — the primitives command_bus.py itself
never had (see reports/USS-TJR-MSN-0210-SUOC-Transition-Architecture.md §4
and the MSN-0210F discovery pass for the full gap list).

Standalone module. NOT wired into command_bus.service or any other live
caller yet — that cutover (and the retirement of command_bus.py's own
_telegram/_slack) is a separate, explicitly-gated Wave 2 follow-up (item E
in the MSN-0210F review), not part of this change.

Slack is included here because both existing senders were reused verbatim
(command_bus.py's `_slack`/`_telegram` HTTP bodies) per Wave 2 direction —
but per the Phase 0 Slack retirement plan, Telegram is the durable
transport; Slack support here should be treated as transitional, not a new
long-term commitment.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"


class Transport(str, Enum):
    TELEGRAM = "telegram"
    SLACK = "slack"  # transitional — see module docstring
    # future: EMAIL, VOICE, PUSH, LCARS (MSN-0210F mission scope)


_TELEGRAM_MAX_LEN = 4096  # Telegram's hard message-length limit; command_bus.py never truncated

TEMPLATES: dict[str, str] = {
    "alert": "\U0001f6a8 *{title}*\n{body}",
    "info": "ℹ️ {title}\n{body}",
    "plain": "{body}",
}


@dataclass
class NotificationResult:
    ok: bool
    transport: Transport
    attempts: int
    error: Optional[str] = None
    sent_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class NotificationLogEntry:
    transport: Transport
    severity: Severity
    title: Optional[str]
    body: str
    result: NotificationResult


_CALL_LOG: list[NotificationLogEntry] = []


def _render(template: str, title: Optional[str], body: str) -> str:
    tpl = TEMPLATES.get(template, TEMPLATES["plain"])
    text = tpl.format(title=title or "", body=body)
    return text[:_TELEGRAM_MAX_LEN]


def _send_telegram(text: str) -> tuple[bool, Optional[str]]:
    """Reuses command_bus.py's _telegram() HTTP body (sendMessage, Markdown)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    raw_ids = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    chat_id = raw_ids.split(",")[0].strip() if raw_ids else os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False, "missing TELEGRAM_BOT_TOKEN or chat id"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _send_slack(text: str) -> tuple[bool, Optional[str]]:
    """Reuses command_bus.py's _slack() HTTP body (chat.postMessage)."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = (
        os.environ.get("BRIEF_CHANNEL")
        or os.environ.get("BRIEF_USER_ID")
        or os.environ.get("CAPTAINS_INBOX_CHANNEL_ID")
        or ""
    )
    if not token or not channel:
        return False, "missing SLACK_BOT_TOKEN or channel"
    url = "https://slack.com/api/chat.postMessage"
    payload = json.dumps({"channel": channel, "text": text}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if not body.get("ok"):
                return False, f"slack_api_error:{body.get('error')}"
            return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


_SENDERS = {
    Transport.TELEGRAM: _send_telegram,
    Transport.SLACK: _send_slack,
}


def notify(
    body: str,
    *,
    title: Optional[str] = None,
    severity: Severity = Severity.INFO,
    template: str = "plain",
    transport: Transport = Transport.TELEGRAM,
    max_retries: int = 1,
    retry_backoff_seconds: float = 2.0,
) -> NotificationResult:
    """Send a notification through the given transport.

    Standalone call — not yet invoked by any production code path. Retries
    up to max_retries times (command_bus.py's senders never retried at all).
    """
    sender = _SENDERS.get(transport)
    if sender is None:
        result = NotificationResult(ok=False, transport=transport, attempts=0, error="transport not implemented")
        _CALL_LOG.append(NotificationLogEntry(transport, severity, title, body, result))
        return result

    text = _render(template, title, body)
    ok = False
    error: Optional[str] = None
    attempts = 0
    for attempt in range(max_retries + 1):
        attempts += 1
        ok, error = sender(text)
        if ok or attempt >= max_retries:
            break
        time.sleep(retry_backoff_seconds)

    result = NotificationResult(ok=ok, transport=transport, attempts=attempts, error=error)
    _CALL_LOG.append(NotificationLogEntry(transport, severity, title, body, result))
    if not ok:
        log.warning("[notification-service] send failed after %d attempt(s) via %s: %s", attempts, transport.value, error)
    return result


def get_call_log(limit: int = 50) -> list[NotificationLogEntry]:
    """In-process call log, most recent last. Not yet persisted to Supabase —
    see Audit Service (core/platform/audit_service.py) for the durable path,
    not yet wired into notify() either per Wave 2 scope."""
    return _CALL_LOG[-limit:]


__all__ = [
    "notify",
    "Severity",
    "Transport",
    "NotificationResult",
    "NotificationLogEntry",
    "get_call_log",
    "TEMPLATES",
]
