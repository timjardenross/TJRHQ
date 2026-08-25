"""
RESIL-INFRA narrative synthesis — ADR-024 (Resilience Intelligence Convergence) fix #5.

Closes the one gap the convergence audit found: domain_heartbeats /
verification_state (migration 0071, core/platform/verification_engine.py)
compute a structured sure/unsure state and a degraded_domains list, but
nothing narrates what that means — RESIL-EXT (intelligence/brief/
brief_generator.py) and RESIL-HUMAN (core/health/weekly_synthesis.py) both
produce a Captain-facing narrative from their structured signal; internal
platform self-health never did.

Deliberately cheap in the common case: when verification_state is 'sure'
(no degraded domains), no LLM call is made at all — there is nothing to
narrate. An LLM is only invoked when something is actually degraded, using
the shared request primitives from core/llm/provider_chain.py (ADR-024
fix #4) rather than a third bespoke provider implementation.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heartbeat import supabase_get  # noqa: E402

from core.llm.provider_chain import call_gemini, call_mistral, call_ollama

log = logging.getLogger("infra-narrative")

_GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
_MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL    = os.getenv("OLLAMA_INFRA_MODEL") or os.getenv("OLLAMA_MODEL", "qwen3:8b")

_SYSTEM_PROMPT = (
    "You are the Verification Engine Officer for USS Starship Endeavour. "
    "You narrate internal platform self-health for Captain TJR: which domains "
    "(data sources, internal jobs, infra signals) are degraded, since when, and "
    "the likely operational impact. "
    "Rules: only use the domain data provided — never invent a cause, and never "
    "state that something 'is already being monitored and handled automatically' "
    "unless the provided domain data literally says so — you have no evidence of "
    "that otherwise, and asserting it as reassurance would be fabricating a fact. "
    "Critical distinction: never_succeeded means this specific monitoring check "
    "has never reported a heartbeat — it is a gap in instrumentation, NOT proof "
    "that the underlying data or job itself doesn't exist or has never run. Do "
    "not claim 'no data has ever been recorded' or similar from never_succeeded "
    "alone — say precisely what you know: the monitor has never heard from this "
    "domain, real status unconfirmed either way. "
    "Each domain includes its own registry `notes` plus expected_cadence_minutes/"
    "grace_period_minutes — read them. A domain whose notes describe it as "
    "event-driven, Captain-paced, or usage-driven (e.g. 'fires when the Captain "
    "captures something') being stale for a few days is normal idle behaviour, "
    "not degradation — say so plainly instead of using alarmed language, and "
    "do not recommend a fix for a domain that isn't actually broken. Reserve "
    "urgent language for domains whose notes describe a fixed automated "
    "schedule (a daily/hourly job) that has gone quiet past its own cadence. "
    "Be direct, specific, and brief (2-4 sentences). "
    "Plain English, no caveats about your own uncertainty. "
    "Always end with one explicit line stating either a concrete next step the "
    "Captain could take (e.g. 'worth checking why X's heartbeat was never wired "
    "in'), or plainly that this is a known monitoring gap with unconfirmed real "
    "impact rather than a confirmed failure."
)

_NOMINAL_NARRATIVE = "All platform domains reporting normally — no degraded signals."


def _latest_verification_state() -> Optional[dict]:
    try:
        rows = supabase_get("verification_state?order=computed_at.desc&limit=1&select=*")
        return rows[0] if rows else None
    except Exception as exc:
        log.warning("[infra-narrative] failed to read verification_state: %s", exc)
        return None


def _degraded_domain_detail(degraded_domains: list[dict]) -> list[dict]:
    """Enrich the compact {domain_key, display_name} pairs on verification_state
    with last_status/last_error_message/is_stale from domain_heartbeat_latest,
    so the narrative has something to actually explain."""
    keys = [d["domain_key"] for d in degraded_domains if d.get("domain_key")]
    if not keys:
        return []
    in_list = ",".join(keys)
    try:
        rows = supabase_get(
            "domain_heartbeat_latest"
            f"?domain_key=in.({in_list})"
            "&select=domain_key,display_name,category,last_status,last_error_message,"
            "last_success_at,never_succeeded,is_stale,expected_cadence_minutes,grace_period_minutes"
        )
        notes_by_key = {}
        try:
            registry_rows = supabase_get(f"domain_registry?domain_key=in.({in_list})&select=domain_key,notes")
            notes_by_key = {r["domain_key"]: r.get("notes") for r in registry_rows}
        except Exception as exc:
            log.warning("[infra-narrative] failed to read domain_registry notes: %s", exc)
        for row in rows:
            row["notes"] = notes_by_key.get(row["domain_key"])
        return rows
    except Exception as exc:
        log.warning("[infra-narrative] failed to read domain_heartbeat_latest detail: %s", exc)
        return []


def _generate(prompt: str) -> Optional[str]:
    """Try the shared provider chain in order. Never raises — returns None on
    total failure, matching every other narrative generator's fail-open contract."""
    providers = [
        ("gemini-3.5-flash-lite", lambda p: call_gemini(_SYSTEM_PROMPT, p, api_key=_GEMINI_API_KEY, max_output_tokens=512)),
        ("mistral-small",    lambda p: call_mistral(_SYSTEM_PROMPT, p, api_key=_MISTRAL_API_KEY, max_tokens=512)),
        (_OLLAMA_MODEL,      lambda p: call_ollama(_SYSTEM_PROMPT, p, base_url=_OLLAMA_BASE_URL, model=_OLLAMA_MODEL, num_predict=400)),
    ]
    for name, fn in providers:
        try:
            result = fn(prompt)
            if result:
                log.info("[infra-narrative] generated via %s", name)
                return result
        except Exception as exc:
            log.warning("[infra-narrative] provider %s failed: %s", name, exc)
    log.warning("[infra-narrative] all providers failed — narrative unavailable")
    return None


def generate_infra_narrative() -> Optional[dict]:
    """
    Main entry point. Returns a dict:
      {"state": "sure"|"unsure", "narrative": str, "degraded_count": int}
    or None if verification_state has never run / is unreadable — the
    caller (captains_brief.py) treats None as "omit this section", never
    as evidence of a healthy platform.
    """
    state_row = _latest_verification_state()
    if state_row is None:
        return None

    state = state_row.get("state", "unsure")
    degraded = state_row.get("degraded_domains") or []
    if isinstance(degraded, str):
        try:
            degraded = json.loads(degraded)
        except Exception:
            degraded = []

    if state == "sure" or not degraded:
        return {"state": "sure", "narrative": _NOMINAL_NARRATIVE, "degraded_count": 0}

    detail = _degraded_domain_detail(degraded)
    lines = []
    for d in detail or degraded:
        last_success = d.get("last_success_at")
        if last_success:
            try:
                ts = datetime.fromisoformat(str(last_success).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_desc = f"last succeeded {(datetime.now(timezone.utc) - ts).days} day(s) ago ({last_success})"
            except (ValueError, TypeError):
                age_desc = f"last succeeded at {last_success}"
        else:
            age_desc = "has never once succeeded"
        lines.append(
            f"- {d.get('display_name', d.get('domain_key', '?'))} "
            f"(category={d.get('category', '?')}, last_status={d.get('last_status', '?')}, "
            f"error={d.get('last_error_message') or 'none reported'}, "
            f"never_succeeded={d.get('never_succeeded', '?')}, {age_desc}, "
            f"expected_cadence_minutes={d.get('expected_cadence_minutes', '?')}, "
            f"grace_period_minutes={d.get('grace_period_minutes', '?')}, "
            f"registry_notes={d.get('notes') or 'none'})"
        )
    prompt = (
        "The following platform domains are currently degraded (stale or never succeeded):\n"
        + "\n".join(lines)
        + f"\n\nOverall reason: {state_row.get('reason') or 'not specified'}"
    )

    narrative = _generate(prompt) or (
        f"{len(degraded)} domain(s) degraded: "
        + ", ".join(d.get("display_name", d.get("domain_key", "?")) for d in degraded)
        + ". (Narrative generation unavailable — see raw domain list.)"
    )

    return {"state": "unsure", "narrative": narrative, "degraded_count": len(degraded)}
