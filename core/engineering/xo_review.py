"""
XO engineering-review gate for auto-generated version-bump PRs.

Direction (2026-09-26): AI-generated patches may open a draft PR only for
the narrowest, lowest-semantic-risk change class (dependency_releases'
version-bump candidates — see batch_coding.py's _is_version_bump_title),
and even then only after an INDEPENDENT review — never the same model
that wrote the patch grading its own work. This repo's own history is why:
a specialist-skill review once caught another specialist inventing
"Advisory/implementation authority" to self-clear part of a change, and
citing a governance rule with zero footprint in the repo — a model
confidently asserting something false, unchecked, is the actual failure
mode this gate exists to catch, not codegen fidelity alone.

A genuine Claude Code Skill (.claude/skills/xo/SKILL.md) only runs inside
an interactive session — a headless systemd timer can't invoke one. This
module ports that skill's own "Gatekeeper mode" rubric verbatim into a
Model Router task_type (xo-engineering-review, see core/model-router/
app.py's TASK_POLICY) so the same real rubric runs unattended, called the
same way hq-evolution-investigate already is.

Fail-CLOSED, deliberately, unlike most of this codebase's other model
calls: this module IS the safety gate, so a review that couldn't run
(router unreachable, malformed response, timeout) returns verdict="hold"
— an unreviewed change must never look the same as an approved one.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("xo_review")

_ROUTER_URL = "http://127.0.0.1:8891"
_ENDPOINT = "/api/model/xo-engineering-review"
_VALID_VERDICTS = {"approve", "approve_with_changes", "hold"}

# Ported verbatim from .claude/skills/xo/SKILL.md's "Gatekeeper mode"
# section — same four questions, same authority-check framing, same
# "hold your own citations to the same bar" instruction. Keep in sync by
# hand if that skill file changes; there is no automated sync (a headless
# service reading a Claude Skill file at runtime would be a stranger
# coupling than just keeping the two in sync deliberately).
_XO_GATEKEEPER_RUBRIC = """You are the Executive Officer (XO) of USS TJR, in Gatekeeper mode: reviewing an AI-generated code change before it reaches the Captain for a merge/decline decision. This is the real function of "Awaiting XO Approval" in this platform's mission lifecycle — you are the check between a proposed change and it actually being acted on, not a formality.

Don't take the input at face value. Spend real effort verifying the load-bearing claims from what's actually in the diff — rather than judging tone or structure alone. A well-organized change built on a wrong assumption about the file it's editing is exactly what this gate exists to catch.

Answer:
1. VERDICT — exactly one of: approve / approve_with_changes / hold. hold means it does not proceed as-is; say exactly what would flip it.
2. AUTHORITY_CHECK — this change was auto-generated for a narrow, pre-approved class (a dependency version bump only). Confirm the diff actually stays inside that scope — watch specifically for the diff touching anything beyond the version string itself (unrelated code, config, CI/CD, credentials), which would mean it's exceeding the authority it was dispatched under.
3. SPOT_CHECK_FINDINGS — what you can verify from the diff itself: does the version string change match what the mission title claims, is the diff otherwise minimal, does anything in it look truncated or malformed.
4. REASONING — plain, evidence-based, one paragraph. State exactly what you checked, not what you'd like to have checked.

Output ONLY valid JSON, no markdown, no explanation outside the JSON, in this exact shape:
{"verdict": "approve|approve_with_changes|hold", "authority_check": "...", "spot_check_findings": "...", "reasoning": "..."}
"""


def _build_review_prompt(*, diff: str, mission_title: str, mission_summary: str) -> str:
    return (
        f"{_XO_GATEKEEPER_RUBRIC}\n"
        f"MISSION TITLE: {mission_title}\n"
        f"MISSION SUMMARY: {mission_summary}\n\n"
        f"DIFF UNDER REVIEW:\n```diff\n{diff[:8000]}\n```\n"
    )


def _fail_closed(reason: str) -> dict[str, Any]:
    return {
        "verdict": "hold",
        "authority_check": "unavailable",
        "spot_check_findings": "unavailable",
        "reasoning": f"XO review could not run — holding rather than treating this as approved: {reason}",
    }


def review_diff(
    *, diff: str, mission_title: str, mission_summary: str,
    router_url: str = _ROUTER_URL, timeout: int = 180,
) -> dict[str, Any]:
    """Runs the XO gatekeeper rubric against a real diff via the Model
    Router. Returns {"verdict", "authority_check", "spot_check_findings",
    "reasoning"}. Never raises — any failure returns a "hold" verdict
    (see module docstring: this is the safety gate, fail-closed not
    fail-open)."""
    if not diff.strip():
        return _fail_closed("empty diff")

    prompt = _build_review_prompt(diff=diff, mission_title=mission_title, mission_summary=mission_summary)
    url = f"{router_url.rstrip('/')}{_ENDPOINT}"
    payload = json.dumps({"prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - url built from the fixed router_url default (localhost model-router) plus a fixed endpoint literal, not user input
            raw = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        # HTTPError is what urlopen raises for the router's own 500 (its
        # do_POST sends 500 for {"success": False, ...}) — the real reason
        # (missing key, guardrails block, upstream error) is unread in the
        # body unless caught separately from URLError, same pattern
        # router_client.py's _call_router already uses for this router.
        detail = exc.reason
        try:
            parsed = json.loads(exc.read().decode())
            if isinstance(parsed, dict) and parsed.get("error"):
                detail = parsed["error"]
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass
        log.warning(f"XO review HTTP {exc.code}: {detail}")
        return _fail_closed(f"router error: {detail}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning(f"XO review request failed: {exc}")
        return _fail_closed(f"router unreachable: {exc}")
    except json.JSONDecodeError as exc:
        log.warning(f"XO review returned non-JSON transport response: {exc}")
        return _fail_closed("router returned an unparseable response")

    response_text = (raw.get("response") or raw.get("content") or "").strip()
    if not response_text:
        return _fail_closed("router returned an empty response")

    try:
        verdict_obj = json.loads(response_text)
    except json.JSONDecodeError:
        # Same defensive strip other router_client callers use for a model
        # that wraps JSON in a ```fence``` despite being asked not to.
        stripped = response_text.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
        try:
            verdict_obj = json.loads(stripped)
        except json.JSONDecodeError:
            log.warning(f"XO review response was not valid JSON: {response_text[:300]!r}")
            return _fail_closed("model response was not valid JSON")

    verdict = str(verdict_obj.get("verdict", "")).strip().lower()
    if verdict not in _VALID_VERDICTS:
        log.warning(f"XO review returned an unrecognised verdict: {verdict!r}")
        return _fail_closed(f"unrecognised verdict from model: {verdict!r}")

    return {
        "verdict": verdict,
        "authority_check": str(verdict_obj.get("authority_check", "")).strip(),
        "spot_check_findings": str(verdict_obj.get("spot_check_findings", "")).strip(),
        "reasoning": str(verdict_obj.get("reasoning", "")).strip(),
    }
