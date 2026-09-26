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
    r"""True only while pytest is actually executing a test
    (PYTEST_CURRENT_TEST is pytest's own documented signal, set only for
    the duration of each test).

    2026-09-19: originally also matched "unittest" in sys.modules (python -m
    unittest, the other way this repo's tests are run), on the assumption
    that no production module imports unittest itself. That assumption was
    wrong: platform-runtime/.venv's logfire_api package unconditionally does
    `from unittest.mock import patch` at import time, so unittest ends up in
    sys.modules in every live process too — this silently blocked every real
    Resend send from 2026-09-19 to 2026-09-25 (confirmed live: emergency
    alert summaries and Captain's brief emails all failed with this warning
    while RESEND_API_KEY/RESEND_FROM were correctly configured). Dropped the
    sys.modules check; PYTEST_CURRENT_TEST alone still catches the actual
    incident this guard was added for (intelligence/workflow/service.py's
    publish_brief() -> notify_published() -> send_email(), exercised by
    tests/test_intelligence_workflow.py / tests/test_telstra_poc.py)."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


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
