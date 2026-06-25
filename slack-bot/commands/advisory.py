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


def _outcomes():
    import outcomes  # noqa: PLC0415
    return outcomes


def _metrics():
    import metrics  # noqa: PLC0415
    return metrics


def _calibration():
    import calibration  # noqa: PLC0415
    return calibration


def _slackify(md: str) -> str:
    md = md.replace("**", "*")
    out = []
    for line in md.splitlines():
        if line.startswith("# "):
            out.append(f"*{line[2:]}*")
        elif line.startswith("## "):
            out.append(f"*{line[3:]}*")
        else:
            out.append(line)
    return "\n".join(out)[:2900]


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
        text_out = _slackify(_lessons().to_markdown(brief))
        return text_out if text_out.strip() else "*LESSONS*\n\nNo lessons matched that topic."
    except Exception as exc:  # noqa: BLE001
        log.error("[lessons] failed: %s", exc)
        return f"*LESSONS*\n\nAdvisory runtime error: `{exc}`."


def handle_evidence(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    text = (text or "").strip()
    if not text:
        return ("*EVIDENCE*\n\nUsage: `/evidence <question>`\n"
                "Shows historical evidence, related prior decisions and lessons.")
    log.info("[evidence] user=%s q=%r", user_id, text[:80])
    try:
        brief = _service().invoke("evidence", text)
        lines = [f"*EVIDENCE — {text}*", "", brief.get("narrative", "")]
        for d in brief.get("related_decisions", []):
            tag = f" [{d.get('outcome')}]" if d.get("outcome") else ""
            lines.append(f"• `{d.get('decision_id')}`{tag}: {d.get('question')}")
        for l in brief.get("lessons", []):
            lines.append(f"• {l.get('lesson_id')}: {l.get('title')}")
        return "\n".join(lines)[:2900]
    except Exception as exc:  # noqa: BLE001
        log.error("[evidence] failed: %s", exc)
        return f"*EVIDENCE*\n\nAdvisory runtime error: `{exc}`."


def handle_advisory_outcome(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    """`/advisory-outcome <advisory_id|last> <success|failure|partial> [note]`."""
    parts = (text or "").split()
    if len(parts) < 2:
        return ("*ADVISORY OUTCOME*\n\n"
                "Usage: `/advisory-outcome <advisory_id|last> <success|failure|partial> [note]`\n"
                "Closes the advisory loop so the system can learn from what happened.")
    advisory_id, outcome = parts[0], parts[1].lower()
    note = " ".join(parts[2:])
    log.info("[advisory-outcome] user=%s id=%s outcome=%s", user_id, advisory_id, outcome)
    try:
        res = _outcomes().record_outcome(advisory_id, outcome=outcome, feedback=note)
        prefix = "✅" if res.get("ok") else "⚠️"
        return f"*ADVISORY OUTCOME*\n\n{prefix} {res.get('message')}"
    except Exception as exc:  # noqa: BLE001
        log.error("[advisory-outcome] failed: %s", exc)
        return f"*ADVISORY OUTCOME*\n\nAdvisory runtime error: `{exc}`."


def handle_advisor_metrics(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    """`/advisor-metrics [calibration]` — advisory metrics or calibration report."""
    log.info("[advisor-metrics] user=%s arg=%r", user_id, text)
    try:
        if (text or "").strip().lower().startswith("cal"):
            return _slackify(_calibration().to_markdown())
        return _slackify(_metrics().to_markdown())
    except Exception as exc:  # noqa: BLE001
        log.error("[advisor-metrics] failed: %s", exc)
        return f"*ADVISOR METRICS*\n\nAdvisory runtime error: `{exc}`."


def _mod(name: str):
    import importlib  # noqa: PLC0415
    return importlib.import_module(name)


def handle_advisor_scan(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    """`/advisor-scan` — proactive scan: what the system noticed (informational)."""
    log.info("[advisor-scan] user=%s", user_id)
    try:
        proactive = _mod("proactive")
        return _slackify(proactive.to_markdown())
    except Exception as exc:  # noqa: BLE001
        log.error("[advisor-scan] failed: %s", exc)
        return f"*ADVISOR SCAN*\n\nAdvisory runtime error: `{exc}`."


def handle_timeline(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    """`/timeline <question>` — temporal query (what changed / preceded / began / next)."""
    text = (text or "").strip()
    try:
        temporal = _mod("temporal")
        if not text:
            res = temporal.what_changed()
        else:
            q = text.lower()
            if "preced" in q or "before" in q:
                res = temporal.what_preceded(text)
            elif "begin" in q or "start" in q or "when" in q:
                res = temporal.when_did_begin(text)
            elif "next" in q or "happens" in q or "usually" in q:
                res = temporal.what_happens_next(text)
            else:
                res = temporal.what_changed(text) if "chang" in q else temporal.what_preceded(text)
        return _slackify("*TIMELINE*\n\n" + temporal.to_markdown(res))
    except Exception as exc:  # noqa: BLE001
        log.error("[timeline] failed: %s", exc)
        return f"*TIMELINE*\n\nAdvisory runtime error: `{exc}`."


_INTEL_VIEWS = {
    "brief": ("daily_brief", "to_markdown"),
    "picture": ("operating_picture", "to_markdown"),
    "wellness": ("wellness", "to_markdown"),
    "strategic": ("strategic", "to_markdown"),
    "forecast": ("forecast", "to_markdown"),
    "trust": ("data_quality", "to_markdown"),
    "data": ("data_quality", "to_markdown"),
}


def handle_intel(text: str, user_id: str | None = None, channel_id: str | None = None) -> str:
    """`/intel [brief|picture|wellness|strategic|forecast|trust]` — intelligence views."""
    view = (text or "brief").strip().split()[0].lower() if (text or "").strip() else "brief"
    if view not in _INTEL_VIEWS:
        return ("*INTEL*\n\nUsage: `/intel [brief|picture|wellness|strategic|forecast|trust]`\n"
                "Default `brief` = daily intelligence briefing.")
    mod_name, fn = _INTEL_VIEWS[view]
    log.info("[intel] user=%s view=%s", user_id, view)
    try:
        return _slackify(getattr(_mod(mod_name), fn)())
    except Exception as exc:  # noqa: BLE001
        log.error("[intel] failed: %s", exc)
        return f"*INTEL*\n\nAdvisory runtime error: `{exc}`."
