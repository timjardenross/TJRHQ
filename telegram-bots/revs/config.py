"""Environment/config loading for the REVS bot. Fails loudly on anything
safety-relevant that's missing rather than silently degrading — see
scoped_supabase.py's module docstring for why an unscoped or misconfigured
credential is a bigger deal for a public-facing bot than for XO."""

from __future__ import annotations

import os
import sys
import logging

from dotenv import load_dotenv

_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_BOT_DIR))

# Same ordering as tg-xo.service's two EnvironmentFile directives (see
# telegram-bots/xo/DEPLOYMENT.md): shared project config (SUPABASE_URL,
# SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET, embedding provider, etc.) loads
# first, then this bot's own .env (TELEGRAM_BOT_TOKEN) loads second and
# wins on any overlapping key. Mirrored here so `python -m
# telegram_bots.revs.app` works standalone, not only under the systemd
# unit's own EnvironmentFile ordering.
load_dotenv(os.path.join(_REPO_ROOT, "platform-runtime", ".env"))
load_dotenv(os.path.join(_BOT_DIR, ".env"), override=True)

log = logging.getLogger("revs-bot.config")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()

# Comma-separated Telegram user ids allowed to run /admin_* commands
# (currently just diagnostics — this bot has no equivalent of XO's
# mission-governance or host-shell surface). Empty = no admin commands
# reachable, not "everyone allowed" — REVS has no single-owner allowlist
# gate like XO's _global_auth_gate, by design (it's a public bot).
_admin_raw = os.environ.get("REVS_ADMIN_USER_IDS", "").strip()
ADMIN_USER_IDS = {int(x) for x in _admin_raw.split(",") if x.strip().isdigit()}


def require(value: str, name: str) -> str:
    if not value:
        log.error("[config] required env var %s is not set — refusing to start", name)
        sys.exit(1)
    return value
