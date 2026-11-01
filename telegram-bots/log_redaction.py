"""Shared log redaction for Telegram bot tokens.

python-telegram-bot / httpx build URLs like https://api.telegram.org/bot<TOKEN>/getUpdates
(and /file/bot<TOKEN>/...). Any log line, argument, exception message, traceback or
stack that embeds such a URL leaks the token into syslog/journal.

install_token_redaction() does two things:
  * installs a LogRecord factory, so EVERY record is scrubbed at creation time,
    regardless of which logger, handler (existing or added later) or library
    (httpx, httpcore, telegram) emitted it;
  * adds the same filter to every current root handler as a backstop in case
    something else replaces the record factory afterwards.
"""

from __future__ import annotations

import contextlib
import logging
import re
import traceback

# "bot<id>:<secret>" (optionally percent-encoded colon) and a bare "<id>:AA<secret>".
_TG_TOKEN_RE = re.compile(
    r"bot\d{6,12}(?::|%3[Aa])[A-Za-z0-9_-]{30,}|\b\d{8,12}(?::|%3[Aa])AA[A-Za-z0-9_-]{30,}"
)
_REDACTED = "bot<REDACTED>"


def redact_text(text: str) -> str:
    return _TG_TOKEN_RE.sub(_REDACTED, text)


def _redact_arg(arg):
    if isinstance(arg, str):
        return redact_text(arg)
    if isinstance(arg, (int, float, bool, type(None))):
        return arg
    try:
        s = str(arg)
    except Exception:  # noqa: BLE001 - never let logging raise
        return arg
    return redact_text(s) if _TG_TOKEN_RE.search(s) else arg


class RedactTelegramToken(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        with contextlib.suppress(Exception):  # never let logging raise
            self._scrub(record)
        return True

    @staticmethod
    def _scrub(record: logging.LogRecord) -> None:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        elif _TG_TOKEN_RE.search(str(record.msg)):
            record.msg = redact_text(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_arg(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _redact_arg(v) for k, v in record.args.items()}
        # Formatter.format() prefers a cached exc_text over exc_info, so render the
        # traceback ourselves, redact it, and drop exc_info so it cannot be re-rendered raw.
        if record.exc_info:
            ei = record.exc_info
            if isinstance(ei, BaseException):
                ei = (type(ei), ei, ei.__traceback__)
            if not record.exc_text:
                record.exc_text = "".join(traceback.format_exception(*ei)).rstrip("\n")
            record.exc_info = None
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)


_FILTER = RedactTelegramToken()
_installed = False


def install_token_redaction() -> None:
    """Idempotently scrub tokens from all log records process-wide."""
    global _installed
    for h in logging.getLogger().handlers:
        if _FILTER not in h.filters:
            h.addFilter(_FILTER)
    if _installed:
        return
    _installed = True
    old_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        _FILTER.filter(record)
        return record

    logging.setLogRecordFactory(factory)
