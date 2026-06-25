"""Slack advisory actions — USS-TJR-MSN-0092 WP5.

Surfaces the shared Advisory Runtime (core/advisory) in Slack:

    /advisor   <question>   — multi-officer advisory (evidence + lessons + confidence)
    /challenge <question>   — advisory with the red-team review surfaced
    /lessons   <topic>      — historical lessons brief for a topic

These are thin handlers — all logic lives in core/advisory. No advisory
framework is redefined here.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADVISORY = _REPO_ROOT / "core" / "advisory"
if str(_ADVISORY) not in sys.path:
    sys.path.insert(0, str(_ADVISORY))


def _service():
    import service  # noqa: PLC0415
    return service


def _lessons():
    import lessons  # noqa: PLC0415
    return lessons


def handle_advisor(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    text = (text or "").strip()
    if not text:
        return (
            "*ADVISOR*\n\n"
            "Usage: `/advisor <question>`\n"
            "Example: `/advisor Should we prioritise the portal or the Telegram bot next?`\n\n"
            "Returns a multi-officer, evidence-based recommendation with confidence "
            "and related lessons. Advisory only — you decide."
        )
    log.info("[advisor] user=%s q=%r", user_id, text[:80])
    try:
        resp = _service().request_advice(text)
        return resp.to_slack_mrkdwn()
    except Exception as exc:  # noqa: BLE001
        log.error("[advisor] failed: %s", exc)
        return f"*ADVISOR*\n\nAdvisory runtime error: `{exc}`. Try again shortly."


def handle_challenge(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    text = (text or "").strip()
    if not text:
        return (
            "*CHALLENGE*\n\n"
            "Usage: `/challenge <question or recommendation>`\n"
            "Runs a red-team review and surfaces disagreement before you commit."
        )
    log.info("[challenge] user=%s q=%r", user_id, text[:80])
    try:
        resp = _service().request_challenge(text)
        return resp.to_slack_mrkdwn()
    except Exception as exc:  # noqa: BLE001
        log.error("[challenge] failed: %s", exc)
        return f"*CHALLENGE*\n\nAdvisory runtime error: `{exc}`."


def handle_lessons(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    text = (text or "").strip()
    if not text:
        return (
            "*LESSONS*\n\n"
            "Usage: `/lessons <topic>`\n"
            "Example: `/lessons automation rollout`\n\n"
            "Returns prior lessons and similar missions — what happened, what "
            "succeeded, what to avoid."
        )
    log.info("[lessons] user=%s topic=%r", user_id, text[:80])
    try:
        brief = _service().invoke("lessons", text)
        md = _lessons().to_markdown(brief)
        md = md.replace("**", "*")
        out = []
        for line in md.splitlines():
            if line.startswith("# "):
                out.append(f"*{line[2:]}*")
            elif line.startswith("## "):
                out.append(f"*{line[3:]}*")
            else:
                out.append(line)
        text_out = "\n".join(out)
        return text_out[:2900] if text_out.strip() else "*LESSONS*\n\nNo lessons matched that topic."
    except Exception as exc:  # noqa: BLE001
        log.error("[lessons] failed: %s", exc)
        return f"*LESSONS*\n\nAdvisory runtime error: `{exc}`."
