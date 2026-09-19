"""Shared Resend email-send primitive.

First real email channel on the platform (Telegram is the only delivery
channel today — core/command-centre/backend/services/notification-engine.js,
telegram-bots/xo). Deliberately minimal: one function that sends one email
via Resend's REST API (https://api.resend.com/emails), matching the same
never-raise, log-and-return-False fail-open contract every other shared
provider primitive here uses (core/platform/heartbeat.py's supabase_insert,
core/llm/provider_chain.py's call_* functions) — a notification failure
must never break the job that triggered it.

RESEND_FROM (2026-08-27): the production domain (tjrmindbody.com) is not
yet verified in Resend (in progress, broken as of this session) — defaults
to Resend's own onboarding@resend.dev test sender, which only delivers to
the Resend account's own signup email. Set RESEND_FROM once a real domain
is verified.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("resend-email")

# 2026-08-29: migrated onto core/platform/configuration_service.py's
# load_dotenv_files() (see tools/check_config_loaders.py) — this module is
# imported standalone (e.g. by intelligence/emergency_alerts.py run as a
# script), so it can't rely on another module having already populated
# os.environ first; was previously "the same self-contained .env loader as
# core/platform/heartbeat.py" per its own docstring, i.e. a known copy.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from core.platform.configuration_service import load_dotenv_files

load_dotenv_files([_REPO_ROOT / ".env"])

_API_KEY = os.environ.get("RESEND_API_KEY", "")
_DEFAULT_FROM = os.environ.get("RESEND_FROM", "Emergency Alert Hub <onboarding@resend.dev>")


def _running_under_tests() -> bool:
    """True while pytest is actually executing a test (PYTEST_CURRENT_TEST
    is pytest's own documented signal, set only for the duration of each
    test) or when unittest has been imported at all (python -m unittest,
    the other way this repo's tests are run — confirmed via `grep -rl
    "^import unittest\|^from unittest"` that no production module in this
    repo imports unittest itself, so this has no real false-positive risk
    here, unlike a generic "are we in CI" heuristic would).

    2026-09-19: added after intelligence/workflow/service.py's publish_brief()
    unconditionally called notify_published() -> send_email(), and
    tests/test_intelligence_workflow.py / tests/test_telstra_poc.py — which
    exercise that exact path against fixture briefs ({"period_end": "b"},
    {"period_end": "2026-07-11"}) — sent three real emails to the Captain's
    inbox from a plain local test run. That call site is now separately
    gated (only fires for the real SupabaseRepository), but this module is
    the actual network boundary every notification path funnels through —
    gating here protects every current and future caller at once, not just
    the one call site that happened to get caught this time."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "unittest" in sys.modules


def send_email(to: str, subject: str, html: str, from_addr: str | None = None, timeout: int = 15) -> bool:
    """Send one email via Resend. Returns True on success, False on any
    failure (missing key, transport error, non-2xx response, or running
    under a test runner — see _running_under_tests) — never raises."""
    if _running_under_tests() and os.environ.get("RESEND_EMAIL_ALLOW_IN_TESTS", "").strip().lower() not in ("1", "true", "yes"):
        log.warning("[resend-email] running under a test runner — refusing to send a real email "
                    "(set RESEND_EMAIL_ALLOW_IN_TESTS=1 to override for a deliberate live-send test)")
        return False

    if not _API_KEY:
        log.warning("[resend-email] RESEND_API_KEY not configured — email not sent")
        return False

    body = json.dumps({
        "from": from_addr or _DEFAULT_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {_API_KEY}",
            "Content-Type": "application/json",
            # Resend sits behind Cloudflare, which blocks urllib's default
            # "Python-urllib/x.y" User-Agent as a bot signature (confirmed
            # live 2026-08-27: HTTP 403 "error code: 1010" — a Cloudflare
            # error, not a Resend auth/validation error).
            "User-Agent": "USS-TJR-EmergencyAlertHub/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - req.url is the hardcoded https://api.resend.com/emails literal, not user input - reviewed 2026-09-12
            resp.read()
            return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        log.warning("[resend-email] send failed: HTTP %s %s", exc.code, detail[:300])
        return False
    except (urllib.error.URLError, OSError) as exc:
        log.warning("[resend-email] send failed: %s", exc)
        return False
