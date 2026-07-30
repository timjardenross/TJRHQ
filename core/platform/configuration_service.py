"""Configuration Service (SUOC Wave 2 Platform Service, MSN-0210F Part 3).

Consolidates the genuinely-shared pieces of the 8+ independent config.py
implementations found in the MSN-0210F discovery pass — SUPABASE_URL,
SUPABASE_SERVICE_ROLE_KEY (including the SUPABASE_KEY alias telegram-bots/
xo/app.py uses for the same value), and GEMINI_API_KEY — plus a reusable
.env-loading helper that folds together the two safe patterns already used
independently: layered load (local .env first, repo-root .env as fallback,
matching telegram-bot/config.py) and graceful-skip on PermissionError
(matching vm-processing/config.py's handling of an unreadable sibling
service's secrets file).

Everything else found (Telegram tokens/chat-ids, Slack tokens, Mistral
agent IDs, YAML-driven operational tuning for the core/infrastructure/*
workers) stays local to its own service — see the discovery report for why
each of those is legitimately service-specific, not duplicated.

Opt-in only. No existing config.py or app.py has been changed to import
this — each service adopts it when/if its own config module is migrated,
which is separate, explicitly-gated Wave 2/3 work. Importing this module
does not change any running service's behaviour today.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


def load_dotenv_files(paths: list[Path], override: bool = False) -> None:
    """Load one or more .env files, in order, without crashing on a missing
    or unreadable file. First file to define a var wins unless override=True
    (matches telegram-bot/config.py's local-then-repo-root fallback intent).

    Does not require the `dotenv` package — manual parsing, same approach
    vm-processing/config.py already uses, so this has no new dependency.
    """
    for path in paths:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except PermissionError:
            log.info("[configuration-service] Skipping unreadable env file: %s", path)
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if override or key not in os.environ:
                os.environ[key] = value


@dataclass
class SharedConfig:
    supabase_url: str
    supabase_service_role_key: str
    gemini_api_key: str

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


def get_shared_config() -> SharedConfig:
    """Read the genuinely cross-service env vars, normalising the one known
    alias (telegram-bots/xo/app.py uses SUPABASE_KEY for what every other
    service calls SUPABASE_SERVICE_ROLE_KEY)."""
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY", "")
    return SharedConfig(
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_service_role_key=service_role_key,
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
    )


def validate_shared_config(config: SharedConfig | None = None) -> list[str]:
    """Return the names of required shared vars that are missing. Reports
    only — does not raise or exit, so callers keep their own existing
    fail-open/fail-closed policy rather than this service imposing one."""
    config = config or get_shared_config()
    missing = []
    if not config.supabase_url:
        missing.append("SUPABASE_URL")
    if not config.supabase_service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    return missing


__all__ = [
    "load_dotenv_files",
    "SharedConfig",
    "get_shared_config",
    "validate_shared_config",
]
