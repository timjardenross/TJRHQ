"""Configuration + environment loading for the Telegram Chief Engineer agent.

Mirrors the platform-runtime dotenv/validation convention (platform-runtime/app.py): load the
service-local ``.env`` first, fall back to the repo-root ``.env``. Centralises the
allowlist parsing and required-variable validation so ``app.py`` stays thin.
"""

from __future__ import annotations

import os
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parent


def _load_env() -> None:
    """Load .env from the service dir, falling back to the repo root."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    # Load the service-local .env first so its values win, then layer the
    # repo-root .env underneath for shared secrets (GEMINI_API_KEY, SUPABASE_URL,
    # ...). load_dotenv() does not override already-set vars, so local precedence
    # is preserved. (Previously this returned after the local file, so the
    # repo-root fallback never ran and shared secrets were silently missing.)
    local_env = SERVICE_DIR / ".env"
    if local_env.exists():
        load_dotenv(str(local_env))
    repo_env = REPO_ROOT / ".env"
    if repo_env.exists():
        load_dotenv(str(repo_env))


_load_env()


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def allowed_chat_ids() -> set[int]:
    """Parse TELEGRAM_ALLOWED_CHAT_IDS (comma/space separated) into a set of ints.

    Empty set means "no one is allowed" — a deliberately closed default so a
    misconfigured deploy cannot accidentally serve the whole world.
    """
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
    return ids


def is_allowed(chat_id: int | None) -> bool:
    return chat_id is not None and chat_id in allowed_chat_ids()


# Required for the bot to actually run (live connection).
REQUIRED_RUNTIME_VARS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS")


def validate_runtime() -> list[str]:
    """Return a list of missing/empty required runtime vars (empty == OK)."""
    missing = [v for v in REQUIRED_RUNTIME_VARS if not os.environ.get(v, "").strip()]
    if not allowed_chat_ids():
        if "TELEGRAM_ALLOWED_CHAT_IDS" not in missing:
            missing.append("TELEGRAM_ALLOWED_CHAT_IDS (no valid ids parsed)")
    return missing
