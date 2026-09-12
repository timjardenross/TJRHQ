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
entirely. command_bus.py's callers use template="raw" (see `_RAW_TEMPLATES`
below) because they compose a full message that mixes intentional HTML
with dynamic values they've already escaped themselves — not the
title/body-are-plain-content shape the "alert"/"plain" templates assume.

2026-09-08: Slack retired entirely (Captain direction — Slack was
disabled). Telegram is now the only transport this module supports; the
`Transport.SLACK` enum value and `_send_slack()` sender that used to sit
here (transitional, per the Phase 0 Slack retirement plan referenced
above) have been removed.

2026-09-12 (USS-TJR-MSN-0366 Stream 9): Added `Transport.APPRISE` /
`_send_apprise()` as a structural hedge against a repeat of the
2026-09-08 Slack retirement above — that migration meant editing this
module's code (removing `_send_slack()`, rewiring `_SENDERS`) to change
transport. Apprise (https://github.com/caronc/apprise) is a single
library speaking 100+ notification-transport config-URL schemes
(`ntfy://…`, `discord://…`, `mailto://…`, …); `_send_apprise()` reads one
or more of these from the `APPRISE_URLS` env var and never special-cases
a URL's scheme, so the *next* transport swap is a config-string change to
`APPRISE_URLS`, not a code change here. Telegram remains
`notify()`'s default transport — Apprise is available, not yet load-bearing
for any caller as of this date. See `_send_apprise()`'s own docstring and
`knowledge/missions/APPRISE-NOTIFICATION-TRANSPORT-20260912-knowledge-record.md`
(Lesson LL-163) for the real send used to verify this, including the one
genuine limitation hit doing it (this deployment's network egress policy
blocks the public ntfy.sh host itself — the code path was still verified
for real, against a self-hosted ntfy-protocol endpoint).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

log = logging.getLogger(__name__)


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"


class Transport(str, Enum):
    TELEGRAM = "telegram"
    APPRISE = "apprise"  # config-URL fan-out via the `apprise` library — see module header, 2026-09-12
    # future: EMAIL, VOICE, PUSH, LCARS (MSN-0210F mission scope) — several
    # of these can likely route through APPRISE_URLS instead of a bespoke
    # sender each; see _send_apprise()'s docstring.


_TELEGRAM_MAX_LEN = 4096  # Telegram's hard message-length limit; command_bus.py never truncated

TEMPLATES: dict[str, str] = {
    "alert": "\U0001f6a8 <b>{title}</b>\n{body}",
    "info": "ℹ️ {title}\n{body}",
    "plain": "{body}",
    "raw": "{body}",
}

# Severity-to-emoji: used only by _render_for_apprise() below to give the
# "plain" template (TEMPLATES' only entry with no built-in emoji) a severity
# cue on transports that don't get one from the template text itself.
# "alert"/"info" already bake their own emoji into TEMPLATES above; "raw" is
# caller-composed (see _RAW_TEMPLATES) and deliberately left untouched here
# too. Not consulted for Telegram at all — Telegram's rendering is entirely
# TEMPLATES-driven, unchanged by this addition.
_SEVERITY_EMOJI: dict[Severity, str] = {
    Severity.INFO: "ℹ️",  # ℹ️  (matches TEMPLATES["info"])
    Severity.WARNING: "⚠️",  # ⚠️
    Severity.ALERT: "\U0001f6a8",  # 🚨  (matches TEMPLATES["alert"])
    Severity.CRITICAL: "\U0001f525",  # 🔥
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
    """Verification convention (council follow-up 2026-08-29 — "verified
    live" claims need repeatable evidence, not just prose): when a session
    claims a Telegram send was "verified live," the evidence is this
    result's own `ok` and `message_id` — cite the actual message_id in the
    claim (e.g. commit message, conversation), not just the word
    "verified." A `message_id` is only present on a real, accepted
    Telegram API response; it cannot be fabricated by a log line printing
    "sent" without the send actually happening."""
    ok: bool
    transport: Transport
    attempts: int
    error: Optional[str] = None
    sent_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    message_id: Optional[int] = None  # Telegram message_id, when the transport returns one.
    # Apprise's fan-out notify() call returns a bare bool across every
    # config URL it holds, not a per-message id the way Telegram's
    # sendMessage response does — this stays None for Transport.APPRISE by
    # design (see _send_apprise()), not because the send wasn't real. A
    # verified-live Apprise claim's evidence is `ok` plus the receiving
    # transport's OWN delivery record (e.g. an ntfy topic's `/json?poll=1`
    # response) — same "don't just say verified" standard as the
    # message_id convention above, applied to a transport that has no
    # message_id to cite.


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


def _render(template: str, title: Optional[str], body: str, severity: Severity = Severity.INFO) -> str:
    """Telegram's renderer. `severity` is accepted-but-unused — present only
    so this has the same signature as _render_for_apprise() and both can
    sit in _RENDERERS below without notify() needing a transport-specific
    branch to call one or the other."""
    return _render_full(template, title, body)[:_TELEGRAM_MAX_LEN]


def _render_for_apprise(template: str, title: Optional[str], body: str, severity: Severity = Severity.INFO) -> str:
    """Apprise-bound transports (ntfy, Discord, email, ...) don't understand
    Telegram's HTML parse_mode — the raw `<b>`/`<code>` tags TEMPLATES bakes
    in for Telegram would otherwise show up as literal angle-bracket text
    on e.g. an ntfy push. Reuses the SAME TEMPLATES/_RAW_TEMPLATES registry
    _render_full already renders from (this module has exactly one template
    registry — see the module header's stance on not duplicating primitives
    across transports), then converts that Telegram-HTML rendering to plain
    text:

      - tags are stripped outright (the formatting itself has no plain-text
        equivalent worth inventing)
      - the &amp;/&lt;/&gt; entities `_escape_telegram_html` applied are
        unescaped back to &/</>, since Apprise sends are plain text, not
        HTML, and a caller's literal "&" should not arrive as "&amp;"

    "plain" (TEMPLATES' only template with no built-in emoji) gets a
    severity emoji prefixed via _SEVERITY_EMOJI so a bare notify(body=...)
    call still carries an urgency cue on transports like ntfy that show
    the message text and nothing else — "alert"/"info" already bake one in
    via TEMPLATES, and "raw" is caller-composed and left untouched.

    No _TELEGRAM_MAX_LEN truncation here — that limit is Telegram's, not a
    property of Apprise or of whatever transport APPRISE_URLS points at.
    """
    rendered = _render_full(template, title, body)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", rendered)
    for ch, esc in _TELEGRAM_HTML_SPECIAL:
        text = text.replace(esc, ch)
    if template == "plain":
        emoji = _SEVERITY_EMOJI.get(severity, "")
        text = f"{emoji} {text}".strip() if emoji else text
    return text


_RENDERERS: dict[Transport, Callable[[str, Optional[str], str, Severity], str]] = {
    Transport.TELEGRAM: _render,
    Transport.APPRISE: _render_for_apprise,
}


def _send_telegram(
    text: str,
    reply_markup: Optional[dict] = None,
    chat_id: Optional[str] = None,
    severity: Severity = Severity.INFO,
) -> tuple[bool, Optional[str], Optional[int]]:
    """Sends via Telegram's HTML parse_mode (2026-08-22, switched from
    Markdown — see _escape_telegram_html's docstring for why).

    reply_markup (optional) attaches an inline keyboard — used by Phase B to add
    the RED-alert [VERIFY NOW] deep-link button.

    chat_id (optional) overrides the env-resolved default — 2026-08-29,
    added so per-recipient callers (e.g. a build-approval confirmation
    going back to whichever chat requested it, or an escalation channel
    that's deliberately not the default captain chat) can still use this
    canonical sender instead of hand-rolling their own.

    severity is accepted-but-unused here (Telegram's rendering is entirely
    TEMPLATES-driven, already baked into `text` by the time this is called)
    — present only so every entry in _SENDERS shares one call signature;
    see _send_apprise() for the transport that actually reads it."""
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
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 - url is api.telegram.org with a fixed path template, TELEGRAM_BOT_TOKEN is a trusted env credential - reviewed 2026-09-12
            parsed = json.loads(resp.read())
            message_id = (parsed.get("result") or {}).get("message_id")
            return True, None, message_id
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", None


_SEVERITY_TO_APPRISE_TYPE: dict[Severity, str] = {
    # Apprise's NotifyType is a plain str-enum ("info"/"success"/"warning"/
    # "failure" — see apprise.common.NotifyType); using the raw strings here
    # keeps `apprise` an import local to _send_apprise() (see its docstring)
    # instead of a module-level import this whole file would otherwise pay
    # for even when Transport.APPRISE is never used.
    Severity.INFO: "info",
    Severity.WARNING: "warning",
    Severity.ALERT: "failure",
    Severity.CRITICAL: "failure",
}


def _send_apprise(
    text: str,
    reply_markup: Optional[dict] = None,
    chat_id: Optional[str] = None,
    severity: Severity = Severity.INFO,
) -> tuple[bool, Optional[str], Optional[int]]:
    """Sends through Apprise (https://github.com/caronc/apprise) — one
    library fanning out to 100+ notification transports (ntfy, Discord,
    Slack, generic email, SMS gateways, ...) selected ENTIRELY by the shape
    of the config URL(s) in the `APPRISE_URLS` env var (comma-separated for
    more than one target), never by transport-specific code in this
    function. This is the whole point of adopting Apprise per USS-TJR-MSN-0366
    Stream 9 — a hedge against a repeat of the 2026-09-08 Slack-retirement
    migration this module's header documents, where changing the active
    transport meant deleting and rewriting a sender here. With Apprise, the
    next transport swap is:

        APPRISE_URLS="ntfy://ntfy.sh/some-topic"
        # ...becomes, with no code change at all...
        APPRISE_URLS="discord://webhook_id/webhook_token"

    so this function must never branch on a URL's scheme, host, or any
    other transport-identifying detail — doing so would silently recreate
    the exact coupling Apprise exists to remove.

    reply_markup and chat_id are accepted only for call-signature parity
    with every other _SENDERS entry (see _send_one) — Apprise has no
    equivalent of Telegram's inline keyboard, and per-recipient targeting
    is the config URL's own job (a caller needing a different recipient
    uses a different APPRISE_URLS value), not a per-call override. Both
    are ignored here.

    severity maps to Apprise's own NotifyType (info/warning/failure) via
    _SEVERITY_TO_APPRISE_TYPE — transports that render an icon/color from
    it (e.g. ntfy's priority-tinted notification, Discord's embed color)
    pick that up automatically; transports that ignore NotifyType are
    unaffected. `text` itself is expected to already be transport-neutral
    plain text — see _render_for_apprise(), which notify() runs for
    Transport.APPRISE instead of Telegram's HTML-producing _render().
    """
    try:
        import apprise
    except ImportError as exc:
        return False, f"apprise not installed: {exc}", None

    raw_urls = os.environ.get("APPRISE_URLS", "")
    urls = [u.strip() for u in raw_urls.split(",") if u.strip()]
    if not urls:
        return False, "missing APPRISE_URLS", None

    apobj = apprise.Apprise()
    for url in urls:
        if not apobj.add(url):
            return False, f"invalid or unrecognised APPRISE_URLS entry: {url}", None

    notify_type = _SEVERITY_TO_APPRISE_TYPE.get(severity, "info")
    try:
        ok = apobj.notify(body=text, notify_type=notify_type)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}", None

    # Apprise's fan-out notify() returns one bare bool across every config
    # URL it holds — no per-message id the way Telegram's sendMessage
    # response carries one (see NotificationResult's field comment on why
    # that's a deliberate, not missing, difference). `ok` is False both
    # when every target failed AND when apobj held zero valid targets, but
    # the "missing/invalid APPRISE_URLS" cases above are already caught
    # earlier with a more specific error than a bare "returned False".
    return bool(ok), (None if ok else "apprise notify() returned False (see logs for the per-target reason)"), None


_SENDERS = {
    Transport.TELEGRAM: _send_telegram,
    Transport.APPRISE: _send_apprise,
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

    chat_id: override the env-resolved default recipient. For a caller
    that targets a different chat per call (e.g. per-requester build
    confirmations, a fixed escalation channel), not the single default
    chat this module otherwise assumes.

    chunk: split `body` across multiple messages at Telegram's 4096-char
    limit (word-boundary cuts, never mid-word) instead of the default
    hard truncation — for callers whose content can legitimately run long
    (e.g. a multi-paragraph daily brief) where truncating would cut real
    content rather than an edge case. Returns the result of the LAST
    chunk sent (an early chunk failing does not raise — see the note
    below).
    """
    sender = _SENDERS.get(transport)
    if sender is None:
        result = NotificationResult(ok=False, transport=transport, attempts=0, error="transport not implemented")
        _CALL_LOG.append(NotificationLogEntry(transport, severity, title, body, result))
        return result

    render = _RENDERERS.get(transport, _render)
    text = render(template, title, body, severity)

    if chunk and transport == Transport.TELEGRAM and len(_render_full(template, title, body)) > _TELEGRAM_MAX_LEN:
        # Chunking at Telegram's exact 4096-char limit is Telegram-specific
        # (guarded by transport == Transport.TELEGRAM above) — other
        # transports' limits vary too widely to share one chunk size, and
        # no caller has needed chunking on Transport.APPRISE yet.
        # _render already truncated to _TELEGRAM_MAX_LEN — chunk the raw
        # body instead, then render each piece (template wrapping is
        # cheap/idempotent per chunk).
        chunks = _split_at_word_boundary(body, _TELEGRAM_MAX_LEN)
        result = None
        for i, piece in enumerate(chunks):
            piece_title = title if i == 0 else None
            piece_text = _render(template, piece_title, piece)
            result = _send_one(sender, piece_text, reply_markup, chat_id, max_retries, retry_backoff_seconds, transport, severity)
            _CALL_LOG.append(NotificationLogEntry(transport, severity, piece_title, piece, result))
            if not result.ok:
                log.warning("[notification-service] chunk %d/%d failed via %s: %s", i + 1, len(chunks), transport.value, result.error)
        return result

    result = _send_one(sender, text, reply_markup, chat_id, max_retries, retry_backoff_seconds, transport, severity)
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


def _send_one(
    sender, text: str, reply_markup, chat_id, max_retries, retry_backoff_seconds, transport: Transport,
    severity: Severity = Severity.INFO,
) -> NotificationResult:
    ok = False
    error: Optional[str] = None
    message_id: Optional[int] = None
    attempts = 0
    for attempt in range(max_retries + 1):
        attempts += 1
        ok, error, message_id = sender(text, reply_markup, chat_id, severity)
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
