"""Adapter: a structured, per-chunk Telegram send result built on top of the platform ``notify`` as it exists today.

Legacy ``notify(chunk=True)`` returns only the LAST chunk's result, keeps sending after an earlier chunk failed,
and its default retry can re-send after a timeout whose outcome is unknown. This adapter therefore calls ``notify``
ONE PIECE AT A TIME (chunk=False, max_retries=0), classifies each result itself, and retries only when the failure
is a definite non-delivery. The native opt-in equivalent is ``notify(..., strict=True)`` (additive; see
docs/intelligence/NOTIFY-STRUCTURED-RESULT-SPEC.md); ``chunks_from_notification`` maps its result onto the delivery
record. The error classification is shared with the platform (``classify_send_error``).
"""
from __future__ import annotations

import time
from collections.abc import Callable

from intelligence.delivery_record import (
    CHUNK_CONFIRMED,
    CHUNK_FAILED,
    CHUNK_UNKNOWN,
    ChunkResult,
    utcnow,
)

TELEGRAM_LIMIT = 4096


def classify_notify_result(ok: bool, message_id: int | None, error: str | None) -> tuple[str, bool]:
    """Return (chunk_state, retry_safe). Anything not provably undelivered is UNKNOWN (never retried blindly).
    The error classification itself lives next to the sender (``notification_service.classify_send_error``) so the
    platform's strict mode and this adapter cannot drift apart."""
    if ok:
        if message_id is None:
            # Acceptance with no provider message id is not evidence of delivery: it is recorded UNKNOWN, never CONFIRMED.
            return CHUNK_UNKNOWN, False
        return CHUNK_CONFIRMED, False
    from core.platform.notification_service import classify_send_error
    return classify_send_error(error)


def chunks_from_notification(result) -> list[ChunkResult]:
    """Map a strict-mode ``NotificationResult.chunk_results`` onto delivery_record ChunkResults (same state names).
    Raises ValueError when the result carries no per-chunk detail (a legacy call): the caller must not guess."""
    cr = getattr(result, "chunk_results", None)
    if not cr:
        raise ValueError("notification result has no chunk_results (call notify(..., strict=True))")
    return [ChunkResult(c.index, c.state, message_id=c.message_id, error=c.error or c.note, attempts=c.attempts, at=c.sent_at)
            for c in cr]


def _redact(text: str) -> str:
    """Provider error text is persisted in attempt records and the local ledger: remove URLs, bot tokens and long opaque strings from it."""
    try:
        from core.platform.notification_service import _redact_error
        return _redact_error(text)
    except Exception:  # noqa: BLE001 - platform module unavailable: minimal local redaction
        import re
        return re.sub(r"[A-Za-z][A-Za-z0-9+.-]{1,30}://\S+", "<url redacted>", text)


def split_for_telegram(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """The platform's own HTML-aware splitter, so chunk boundaries match what notify(chunk=True) produces today."""
    if len(text) <= limit:
        return [text]
    from core.platform import notification_service as ns
    return list(ns._split_html_aware(text, limit))


def make_telegram_sender(*, notify_fn: Callable | None = None, sleep: Callable[[float], None] = time.sleep,
                         retry_backoff_seconds: float = 2.0, max_definite_retries: int = 1) -> Callable[[str], ChunkResult]:
    """Return ``send_chunk(piece) -> ChunkResult`` for ``delivery_record.deliver``. ``notify_fn`` is injectable so tests
    mock the transport; the default imports the real ``notify`` lazily (and is never called by tests)."""
    def _send(piece: str) -> ChunkResult:
        fn = notify_fn
        if fn is None:
            from core.platform.notification_service import Transport
            from core.platform.notification_service import notify as fn_real
            fn = lambda body: fn_real(body, template="raw", transport=Transport.TELEGRAM, chunk=False, max_retries=0)
        attempts = 0
        while True:
            attempts += 1
            try:
                r = fn(piece)
            except Exception as exc:  # noqa: BLE001 - raising after the request may have been written is ambiguous
                return ChunkResult(0, CHUNK_UNKNOWN, error=type(exc).__name__, attempts=attempts, at=utcnow())
            state, retry_safe = classify_notify_result(bool(getattr(r, "ok", False)), getattr(r, "message_id", None), getattr(r, "error", None))
            if state == CHUNK_FAILED and retry_safe and attempts <= max_definite_retries:
                sleep(retry_backoff_seconds)
                continue
            err = None if state == CHUNK_CONFIRMED else (_redact(str(getattr(r, "error", "") or ""))[:200]
                                                         or ("accepted_without_message_id" if getattr(r, "ok", False) else "no_error_detail"))
            return ChunkResult(0, state, message_id=getattr(r, "message_id", None) if state == CHUNK_CONFIRMED else None,
                               error=err, attempts=attempts, at=utcnow())
    return _send
