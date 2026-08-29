"""Notification Service (SUOC Wave 2 Platform Service, MSN-0210F Part 2).

Generalises core/coordination/command_bus.py's private `_telegram`/`_slack`
senders into a proper service: severity-as-real-data (not ad-hoc strings),
a small message-template registry, delivery-status tracking, retry with
backoff, and an in-process call log — the primitives command_bus.py itself
never had (see reports/USS-TJR-MSN-0210-SUOC-Transition-Architecture.md §4
and the MSN-0210F discovery pass for the full gap list).

2026-08-22 Wave 2 cutover (item E): command_bus.py's real ALERT/CRITICAL
sends now go through notify() via its `_route()` (see command_bus.py's
`_route()` docstring) — `_telegram()` has been retired from command_bus.py
entirely. `_slack()` is still defined there and used directly by one
non-ALERT/CRITICAL caller (`_rule_new_missions`'s Idea-triage nudge),
which was out of scope for this cutover. command_bus.py's callers use
template="raw" (see `_RAW_TEMPLATES` below) because they compose a full
message that mixes intentional Markdown with dynamic values they've
already escaped themselves — not the title/body-are-plain-content shape
the "alert"/"plain" templates assume.

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
    "alert": "\U0001f6a8 <b>{title}</b>\n{body}",
    "info": "ℹ️ {title}\n{body}",
    "plain": "{body}",
    "raw": "{body}",
}

# Templates whose body is ALREADY fully rendered by the caller — intentional
# HTML markup (<b>, <code>) interleaved with dynamic values the caller has
# already escaped itself, value-by-value, before composing the string. This
# is the shape command_bus.py's alert messages take (see its `_esc_html()`
# and `_route()`): unlike "plain" (a pure unformatted string that this
# module must escape wholesale), a "raw" body must NOT be run through
# `_escape_telegram_html()` again — that would double-escape the caller's
# already-escaped dynamic values while ALSO escaping the caller's
# intentional <b>/<code> markers, breaking formatting outright.
_RAW_TEMPLATES = {"raw"}


@dataclass
class NotificationResult:
    ok: bool
    transport: Transport
    attempts: int
    error: Optional[str] = None
    sent_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    message_id: Optional[int] = None  # Telegram message_id, when the transport returns one; None for Slack


@dataclass
class NotificationLogEntry:
    transport: Transport
    severity: Severity
    title: Optional[str]
    body: str
    result: NotificationResult


_CALL_LOG: list[NotificationLogEntry] = []


# 2026-08-22, corrected same day: first attempt escaped for legacy Telegram
# "Markdown" parse_mode (backslash before _, *, `, [) — that stopped the
# HTTP 400 hard-reject, but real-device verification (Captain checked an
# actual delivered message) showed the backslashes render as LITERAL
# visible characters ("req\_verify\_..."), not consumed as escapes. Legacy
# Markdown's backslash-escaping does not behave the way Telegram's own docs
# and every reference on it implies — confirmed by two independent real
# sends, not assumed. An `ok: true` API response only proves Telegram
# accepted and parsed the message; it does NOT prove the visual rendering
# is correct, which is the actual mistake behind the first attempt.
#
# Switched the whole module (TEMPLATES above and _send_telegram below) from
# parse_mode="Markdown" to parse_mode="HTML" instead of trying to fix the
# Markdown escaping further — HTML mode's escaping rules are simple and
# unambiguous (only &, <, > need escaping, no interaction with formatting
# syntax), and this exact mode is already proven working elsewhere in this
# codebase (intelligence/captains_brief.py's _send_telegram(),
# telegram-bots/xo/app.py). Order matters: & must be escaped first, or the
# &amp;/&lt;/&gt; this function inserts would themselves get re-escaped.
_TELEGRAM_HTML_SPECIAL = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))


def _escape_telegram_html(text: str) -> str:
    for ch, esc in _TELEGRAM_HTML_SPECIAL:
        text = text.replace(ch, esc)
    return text


def _render_full(template: str, title: Optional[str], body: str) -> str:
    """Renders without the _TELEGRAM_MAX_LEN truncation _render() applies —
    used by notify(chunk=True) to measure/split the real length before
    deciding whether truncation would even happen."""
    tpl = TEMPLATES.get(template, TEMPLATES["plain"])
    if template in _RAW_TEMPLATES:
        # Caller already escaped dynamic content and composed the final
        # HTML itself — pass through untouched (see _RAW_TEMPLATES doc).
        return tpl.format(title=title or "", body=body)
    return tpl.format(
        title=_escape_telegram_html(title or ""),
        body=_escape_telegram_html(body),
    )


def _render(template: str, title: Optional[str], body: str) -> str:
    return _render_full(template, title, body)[:_TELEGRAM_MAX_LEN]


def _send_telegram(
    text: str, reply_markup: Optional[dict] = None, chat_id: Optional[str] = None
) -> tuple[bool, Optional[str], Optional[int]]:
    """Sends via Telegram's HTML parse_mode (2026-08-22, switched from
    Markdown — see _escape_telegram_html's docstring for why). NOTE: `text`
    is shared with _send_slack() below via the same _render() output —
    Slack's mrkdwn doesn't understand <b>/<code> tags, so Slack messages
    will show literal tag characters until Slack gets its own rendering
    path. Not fixed here: this module's own docstring already treats Slack
    as transitional and Telegram as the durable transport; the previous
    Markdown asterisks happened to double as valid Slack mrkdwn by
    coincidence, HTML tags don't have an equivalent coincidence.

    reply_markup (optional) attaches an inline keyboard — used by Phase B to add
    the RED-alert [VERIFY NOW] deep-link button.

    chat_id (optional) overrides the env-resolved default — 2026-08-29,
    added so per-recipient callers (e.g. a build-approval confirmation
    going back to whichever chat requested it, or an escalation channel
    that's deliberately not the default captain chat) can still use this
    canonical sender instead of hand-rolling their own."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if chat_id is None:
        raw_ids = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
        chat_id = raw_ids.split(",")[0].strip() if raw_ids else os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False, "missing TELEGRAM_BOT_TOKEN or chat id", None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body_obj = {
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": True,  # matches every caller migrated onto this sender so far
    }
    if reply_markup:
        body_obj["reply_markup"] = reply_markup
    payload = json.dumps(body_obj).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            parsed = json.loads(resp.read())
            message_id = (parsed.get("result") or {}).get("message_id")
            return True, None, message_id
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", None


def _send_slack(
    text: str, reply_markup: Optional[dict] = None, chat_id: Optional[str] = None
) -> tuple[bool, Optional[str], Optional[int]]:
    """Reuses command_bus.py's _slack() HTTP body (chat.postMessage).
    reply_markup and chat_id are Telegram-specific and ignored here
    (signature parity with _send_telegram). message_id is always None —
    Slack's ts (message timestamp) plays that role but nothing here needs
    it yet; add if a Slack caller needs edit-in-place later."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = (
        os.environ.get("BRIEF_CHANNEL")
        or os.environ.get("BRIEF_USER_ID")
        or os.environ.get("CAPTAINS_INBOX_CHANNEL_ID")
        or ""
    )
    if not token or not channel:
        return False, "missing SLACK_BOT_TOKEN or channel", None
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
                return False, f"slack_api_error:{body.get('error')}", None
            return True, None, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", None


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
    reply_markup: Optional[dict] = None,
    chat_id: Optional[str] = None,
    chunk: bool = False,
) -> NotificationResult:
    """Send a notification through the given transport.

    Used by command_bus.py's ALERT/CRITICAL path and, as of 2026-08-29, the
    consolidated notification-sender migration (see
    tools/check_notification_senders.py) — no longer a standalone call.
    Retries up to max_retries times per chunk (command_bus.py's senders
    never retried at all).

    chat_id: override the env-resolved default recipient (Telegram only;
    ignored by Slack — see _send_slack). For a caller that targets a
    different chat per call (e.g. per-requester build confirmations, a
    fixed escalation channel), not the single default chat this module
    otherwise assumes.

    chunk: split `body` across multiple messages at Telegram's 4096-char
    limit (word-boundary cuts, never mid-word) instead of the default
    hard truncation — for callers whose content can legitimately run long
    (e.g. a multi-paragraph daily brief) where truncating would cut real
    content rather than an edge case. Only affects Telegram; Slack has no
    equivalent hard limit in this module's usage so chunk is a no-op there.
    Returns the result of the LAST chunk sent (an early chunk failing does
    not raise — see the note below).
    """
    sender = _SENDERS.get(transport)
    if sender is None:
        result = NotificationResult(ok=False, transport=transport, attempts=0, error="transport not implemented")
        _CALL_LOG.append(NotificationLogEntry(transport, severity, title, body, result))
        return result

    text = _render(template, title, body)

    if chunk and transport == Transport.TELEGRAM and len(_render_full(template, title, body)) > _TELEGRAM_MAX_LEN:
        # _render already truncated to _TELEGRAM_MAX_LEN — chunk the raw
        # body instead, then render each piece (template wrapping is
        # cheap/idempotent per chunk).
        chunks = _split_at_word_boundary(body, _TELEGRAM_MAX_LEN)
        result = None
        for i, piece in enumerate(chunks):
            piece_title = title if i == 0 else None
            piece_text = _render(template, piece_title, piece)
            result = _send_one(sender, piece_text, reply_markup, chat_id, max_retries, retry_backoff_seconds, transport)
            _CALL_LOG.append(NotificationLogEntry(transport, severity, piece_title, piece, result))
            if not result.ok:
                log.warning("[notification-service] chunk %d/%d failed via %s: %s", i + 1, len(chunks), transport.value, result.error)
        return result

    result = _send_one(sender, text, reply_markup, chat_id, max_retries, retry_backoff_seconds, transport)
    _CALL_LOG.append(NotificationLogEntry(transport, severity, title, body, result))
    if not result.ok:
        log.warning("[notification-service] send failed after %d attempt(s) via %s: %s", result.attempts, transport.value, result.error)
    return result


def _split_at_word_boundary(text: str, limit: int) -> list[str]:
    """Splits text into <=limit-char pieces, cutting at the last space
    before the limit rather than mid-word. Mirrors the fix applied to
    intelligence/captains_brief.py's _truncate_clean/_send_telegram
    (2026-08-29) — a bare text[:limit] slice cuts mid-sentence/mid-word."""
    pieces = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining[:limit].rsplit(" ", 1)[0] or remaining[:limit]
        pieces.append(cut)
        remaining = remaining[len(cut):].lstrip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _send_one(sender, text: str, reply_markup, chat_id, max_retries, retry_backoff_seconds, transport: Transport) -> NotificationResult:
    ok = False
    error: Optional[str] = None
    message_id: Optional[int] = None
    attempts = 0
    for attempt in range(max_retries + 1):
        attempts += 1
        ok, error, message_id = sender(text, reply_markup, chat_id)
        if ok or attempt >= max_retries:
            break
        time.sleep(retry_backoff_seconds)
    return NotificationResult(ok=ok, transport=transport, attempts=attempts, error=error, message_id=message_id)


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
