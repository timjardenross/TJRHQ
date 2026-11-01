"""Environment/config loading for the REVS bot. Fails loudly on anything
safety-relevant that's missing rather than silently degrading — see
scoped_supabase.py's module docstring for why an unscoped or misconfigured
credential is a bigger deal for a public-facing bot than for XO."""

from __future__ import annotations

import logging
import os
import sys

from dotenv import dotenv_values

_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_BOT_DIR))

if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# Same ordering as tg-xo.service's two EnvironmentFile directives (see
# telegram-bots/xo/DEPLOYMENT.md): shared project config (SUPABASE_URL,
# SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET, embedding provider, etc.) loads
# first, then this bot's own .env (TELEGRAM_BOT_TOKEN) loads second and
# wins on any overlapping key. Mirrored here so `python -m
# telegram_bots.revs.app` works standalone, not only under the systemd
# unit's own EnvironmentFile ordering. 2026-08-29: migrated onto
# core/platform/configuration_service.py's load_dotenv_files() — two calls
# (not one list) to preserve "own .env wins over shared" ordering, since
# that module's override flag applies uniformly to a whole call.
from pathlib import Path as _Path

from core.platform.configuration_service import get_shared_config, load_dotenv_files

load_dotenv_files([_Path(_REPO_ROOT) / "platform-runtime" / ".env"])
load_dotenv_files([_Path(_BOT_DIR) / ".env"], override=True)

log = logging.getLogger("revs-bot.config")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
# 2026-09-26: sourced from the shared SUOC config base
# (core/platform/configuration_service.py) rather than reading os.environ
# directly. This bot deliberately does NOT use SUPABASE_SERVICE_ROLE_KEY
# (see scoped_supabase.py's module docstring — a public-facing bot uses a
# scoped anon-key client, not the service role key), so only the URL is
# pulled from the shared base; SUPABASE_ANON_KEY/SUPABASE_JWT_SECRET stay
# local to scoped_supabase.py exactly as before.
SUPABASE_URL = get_shared_config().supabase_url.strip()

# §5.4 escalation: crisis triggers alert the Captain via XO's own bot
# identity/chat, not this bot's. Read directly from telegram-bots/xo/.env
# with dotenv_values() (doesn't touch os.environ) rather than load_dotenv()
# — XO's .env also defines TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID, and a
# normal load_dotenv() here would clobber this bot's OWN
# TELEGRAM_BOT_TOKEN depending on load order. Keeping the two entirely
# separate avoids that footgun regardless of ordering.
_xo_env = dotenv_values(os.path.join(_REPO_ROOT, "telegram-bots", "xo", ".env"))
XO_ESCALATION_BOT_TOKEN = (_xo_env.get("TELEGRAM_BOT_TOKEN") or "").strip()
XO_ESCALATION_CHAT_ID = (_xo_env.get("TELEGRAM_CHAT_ID") or "").strip()


def require(value: str, name: str) -> str:
    if not value:
        log.error("[config] required env var %s is not set — refusing to start", name)
        sys.exit(1)
    return value
