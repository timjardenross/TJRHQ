"""Telegram Access Control (SUOC Wave 2 Platform Service, MSN-0210F Item C).

Canonical chat-ID allowlist gate for Telegram interfaces going forward.
Generalises telegram-bot/config.py's set-based allowed_chat_ids()/is_allowed()
pattern; retires the inline single-ID equality checks that were duplicated
across telegram-bots/xo/app.py's 6 command handlers.

TELEGRAM_ALLOWED_CHAT_IDS (an explicit, operator-managed allowlist) is the
long-term authority model. `bootstrap_captain_chat_id` is a fallback ONLY —
it exists so a service isn't locked out before TELEGRAM_ALLOWED_CHAT_IDS is
configured for it, not as the intended permanent mechanism. Any caller still
relying on the fallback should get an explicit TELEGRAM_ALLOWED_CHAT_IDS of
its own as a follow-up, not keep passing a bootstrap value indefinitely.
"""

from __future__ import annotations

import os


def allowed_chat_ids(bootstrap_captain_chat_id: int | None = None) -> set[int]:
    """The active allowlist: TELEGRAM_ALLOWED_CHAT_IDS if set (comma/space
    separated ints, malformed tokens silently dropped), else a single-id
    set built from bootstrap_captain_chat_id, else empty (closed)."""
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    ids: set[int] = set()
    for token in raw.replace(",", " ").split():
        token = token.strip()
        if not token:
            continue
        try:
            ids.add(int(token))
        except ValueError:
            continue
    if ids:
        return ids
    return {bootstrap_captain_chat_id} if bootstrap_captain_chat_id is not None else set()


def is_allowed(chat_id: int | None, bootstrap_captain_chat_id: int | None = None) -> bool:
    return chat_id is not None and chat_id in allowed_chat_ids(bootstrap_captain_chat_id)


__all__ = ["allowed_chat_ids", "is_allowed"]
