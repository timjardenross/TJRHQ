"""Operational Pattern Library (SUOC Wave 3 Platform Runtime, Workstream E).

First real implementation of the Operational Pattern Library capability.
Patterns are reusable engineering process knowledge extracted from
completed missions — not AI-specific, not tied to any particular agent
implementation. `seed_initial_patterns()` populates the 8 candidate
patterns named in the Wave 3 mission brief, each written from genuine
findings this session (not generic filler).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


def add_pattern(
    pattern_name: str,
    pattern_category: str,
    description: str,
    when_to_use: str,
    steps: list[str],
    source_missions: list[str],
    *,
    confidence: Optional[int] = None,
) -> bool:
    """Add or update a pattern (upsert on pattern_name). Non-blocking."""
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        if not client.is_enabled():
            log.info("[pattern-library] Supabase disabled; pattern not persisted")
            return False
        raw = client.raw_client
        if raw is not None:
            raw.table("operational_patterns").upsert(
                {
                    "pattern_name": pattern_name,
                    "pattern_category": pattern_category,
                    "description": description,
                    "when_to_use": when_to_use,
                    "steps": steps,
                    "source_missions": source_missions,
                    "confidence": confidence,
                },
                on_conflict="pattern_name",
            ).execute()
            return True
        result = client.insert(
            "operational_patterns",
            {
                "pattern_name": pattern_name,
                "pattern_category": pattern_category,
                "description": description,
                "when_to_use": when_to_use,
                "steps": steps,
                "source_missions": source_missions,
                "confidence": confidence,
            },
        )
        return result.ok
    except Exception as exc:
        log.warning("[pattern-library] add_pattern failed (non-blocking): %s", exc)
        return False


def get_patterns(category: Optional[str] = None) -> list[dict[str, Any]]:
    try:
        from tools.supabase.client import CommanderSupabaseClient

        client = CommanderSupabaseClient()
        raw = client.raw_client
        if raw is None:
            return []
        query = raw.table("operational_patterns").select("*")
        if category:
            query = query.eq("pattern_category", category)
        result = query.execute()
        return list(result.data or [])
    except Exception as exc:
        log.warning("[pattern-library] get_patterns failed (non-blocking): %s", exc)
        return []


_INITIAL_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern_name": "Platform Stabilisation",
        "pattern_category": "stabilisation",
        "description": "Audit live system state directly before trusting any documentation or a service's 'enabled' status.",
        "when_to_use": "Before any architecture-consolidation or convergence mission, and periodically as a health check.",
        "steps": [
            "Check systemctl --failed and NRestarts for every service, not just is-active",
            "A service can show 'enabled'/'loaded' while crash-looping tens of thousands of times",
            "Cross-check systemd EnvironmentFile/WorkingDirectory against what actually exists on disk",
            "Verify live Caddy/routing config before assuming an old backend is still receiving traffic",
        ],
        "source_missions": ["Phase 0 Stabilisation (2026-07-05)"],
        "confidence": 90,
    },
    {
        "pattern_name": "Mission Convergence",
        "pattern_category": "convergence",
        "description": "Before generalising an existing implementation as a reuse anchor, verify it against the LIVE schema, not the design doc describing it.",
        "when_to_use": "Any time a mission proposes reusing 'proven' existing code as the template for a new platform service.",
        "steps": [
            "Read the design doc's claimed schema/behaviour",
            "Query information_schema/pg_constraint directly for the real column names, types, and FK targets",
            "Prove the 'proven' pattern actually works with a live write-read-cleanup test before trusting it",
            "If it's broken, fix the anchor itself before generalising it further",
        ],
        "source_missions": ["MSN-0210E (SUOC Wave 1)", "MSN-0210F (SUOC Wave 2)"],
        "confidence": 95,
    },
    {
        "pattern_name": "Platform Readiness Gate",
        "pattern_category": "readiness-gate",
        "description": "A GO/NO-GO decision should check whether open work items structurally overlap with what's being gated, not just whether they exist.",
        "when_to_use": "Before authorising a new wave/phase of work while other threads remain open.",
        "steps": [
            "List every open decision/thread from prior work",
            "For each, check whether it shares files, tables, or services with the new work's actual scope",
            "Open items with no structural overlap don't block — recommend GO WITH CONDITIONS, not NO-GO by default",
            "Name the conditions explicitly so they don't get silently dropped",
        ],
        "source_missions": ["MSN-0210G (Platform Readiness Gate)"],
        "confidence": 85,
    },
    {
        "pattern_name": "SUOC Review",
        "pattern_category": "review",
        "description": "Maintain one living capability registry rather than accumulating an ever-growing pile of point-in-time reports.",
        "when_to_use": "Ongoing — every mission that touches platform architecture.",
        "steps": [
            "Check the Platform Registry first, before re-deriving state from scattered reports",
            "Update the specific capability records a mission actually changes",
            "Record confidence and maturity changes honestly, including regressions",
            "Treat the registry as a release gate, not optional documentation",
        ],
        "source_missions": ["MSN-0210 (SUOC Transition Architecture)", "SUOC Platform Registry v1.0"],
        "confidence": 80,
    },
    {
        "pattern_name": "Build vs Borrow",
        "pattern_category": "build-vs-borrow",
        "description": "Evaluate external frameworks for patterns to borrow, not frameworks to adopt wholesale — then run one small, sunset-gated pilot against a real internal pain point.",
        "when_to_use": "Any time external tooling (agent frameworks, memory systems, orchestration libraries) is proposed as a platform dependency.",
        "steps": [
            "Survey multiple comparable external projects, not just the first one mentioned",
            "Extract specific reusable patterns (file formats, safety rails, gateway models) rather than the whole framework",
            "Decide explicitly: does adopting this recreate a duplicated-platform-service problem we're trying to eliminate?",
            "If a pilot is warranted, scope it small, time-box it, and set an explicit decision gate at the end",
        ],
        "source_missions": ["MSN-0210H (Hermes Build-vs-Borrow Discovery)"],
        "confidence": 85,
    },
    {
        "pattern_name": "Security Review",
        "pattern_category": "security",
        "description": "Credentials leak through two recurring, easy-to-miss channels on this platform: embedded in git remote URLs, and echoed into service startup logs (journalctl).",
        "when_to_use": "Any time git remotes are inspected or a service is restarted for verification.",
        "steps": [
            "Never print git remote -v or journalctl output raw when a token might be embedded — check first, redact if needed",
            "A credential embedded in a git remote URL is a standing exposure, not a one-time leak, until rotated",
            "python-telegram-bot/httpx log the full request URL (including the bot token) at INFO level by default on every API call",
            "Document exposure + rotation procedure even when not rotating immediately — don't let it go untracked",
        ],
        "source_missions": ["Phase 0 (GitHub PAT)", "MSN-0210F Phase 2 (XO bot Telegram token)"],
        "confidence": 90,
    },
    {
        "pattern_name": "Architecture Review",
        "pattern_category": "review",
        "description": "Before building any new platform primitive, grep the whole repo for anything already shaped like it — the closest existing precedent should inform the new design's vocabulary, not be ignored.",
        "when_to_use": "At the start of any new Platform Service or Platform Capability build.",
        "steps": [
            "Search for table/class names matching the new concept's shape (task, event, queue, state)",
            "Read the 2-3 closest existing implementations fully, even if none is a perfect match",
            "Reuse their status vocabulary/ownership model where sensible, rather than inventing a new one",
            "Document explicitly which existing pieces were surveyed and why they weren't simply reused wholesale",
        ],
        "source_missions": ["MSN-0210J (SUOC Wave 3), required architecture review"],
        "confidence": 90,
    },
    {
        "pattern_name": "Engineering Validation",
        "pattern_category": "validation",
        "description": "Never trust a database schema from docstrings or design documents — verify directly against the live database, then prove new code with a real write-read-cleanup cycle.",
        "when_to_use": "Any time new code writes to a Supabase table, especially one referenced by multiple existing modules.",
        "steps": [
            "Query information_schema.columns and pg_constraint for the actual live column names/types/CHECK constraints",
            "Check FK targets explicitly — a column can point to a different table than every doc assumes",
            "Write a real test row, read it back, confirm the values, then delete it",
            "Compile-check every changed file before considering the change done",
        ],
        "source_missions": ["MSN-0210E", "MSN-0210F", "MSN-0210J"],
        "confidence": 95,
    },
]


def seed_initial_patterns() -> int:
    """Populate the 8 candidate patterns named in the Wave 3 mission brief.
    Idempotent (upsert on pattern_name). Returns count successfully written."""
    count = 0
    for pattern in _INITIAL_PATTERNS:
        if add_pattern(**pattern):
            count += 1
    return count


__all__ = ["add_pattern", "get_patterns", "seed_initial_patterns"]
