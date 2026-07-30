"""Pattern Recognition Engine (EXEC-005 WP8).

Identifies recurring organisational themes across Command Memory — repeated
delivery delays, capacity overload, governance exceptions, resilience risks,
architectural debt, communications bottlenecks.

Pattern → Finding → Investigation → Improvement → Mission (if required).

Reuse: decisions table, missions table. No new tables.

Pattern registry (decisions table):
  statement = "[PATTERN] {theme}: {count} occurrence(s) — {description[:60]}"
  owner     = "pattern:{theme}"
  rationale = "THEME: {t} | OCCURRENCES: {n} | WINDOW: {w} | SIGNALS: {s} |
               SEVERITY: {sev} | DETECTED: {ts}"

Public API:
    OrganisationalPattern
    detect_patterns(lookback)        -> list[OrganisationalPattern]
    get_known_patterns(limit)        -> list[OrganisationalPattern]
    pattern_to_investigation(pattern)-> str | None  (inv_id)
    format_patterns(patterns)        -> str
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_BOT), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

PATTERN_OWNER_PREFIX = "pattern:"
_PATTERN_STATEMENT   = "[PATTERN]"

# Theme → signal keywords + the investigation type it maps to.
_THEME_SIGNALS: dict[str, dict[str, Any]] = {
    "delivery_delay": {
        "signals": ["blocked", "stale", "overdue", "delayed", "stuck", "slipped"],
        "inv_type": "operational",
        "label": "Repeated delivery delays",
    },
    "capacity_overload": {
        "signals": ["capacity", "overload", "red status", "amber", "throughput limit", "deferral"],
        "inv_type": "health",
        "label": "Repeated capacity overload",
    },
    "governance_exception": {
        "signals": ["governance exception", "override", "exception approved", "bypass"],
        "inv_type": "strategic",
        "label": "Repeated governance exceptions",
    },
    "resilience_risk": {
        "signals": ["resilience", "red risk", "amber risk", "critical event", "cps230"],
        "inv_type": "resilience",
        "label": "Repeated resilience risks",
    },
    "architectural_debt": {
        "signals": ["architecture decision", "technical debt", "adr", "refactor", "workaround"],
        "inv_type": "architecture",
        "label": "Repeated architectural debt",
    },
    "communications_bottleneck": {
        "signals": ["ready to publish", "awaiting approval", "pipeline", "content backlog"],
        "inv_type": "communications",
        "label": "Repeated communications bottlenecks",
    },
    "knowledge_gap": {
        "signals": ["knowledge gap", "undocumented", "missing rationale", "no record"],
        "inv_type": "knowledge",
        "label": "Repeated knowledge gaps",
    },
}

# Minimum occurrences within the window to qualify as a pattern.
_PATTERN_THRESHOLD = 3


@dataclass
class OrganisationalPattern:
    theme: str
    label: str
    occurrences: int
    window_days: int
    signals_matched: list[str] = field(default_factory=list)
    inv_type: str = "operational"
    detected_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def severity(self) -> str:
        if self.occurrences >= 8:
            return "HIGH"
        if self.occurrences >= 5:
            return "MEDIUM"
        return "LOW"


# ── Detection ─────────────────────────────────────────────────────────────────

def _fetch_recent_text(lookback_days: int) -> list[str]:
    """Gather recent decision statements + mission titles for pattern scanning."""
    texts: list[str] = []
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return texts

        cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).isoformat()

        # Recent decisions (exclude our own pattern registry rows)
        dres = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(300)
            .execute()
        )
        for row in dres.data or []:
            owner = str(row.get("owner") or "")
            if owner.startswith(PATTERN_OWNER_PREFIX):
                continue
            texts.append(f"{row.get('statement','')} {row.get('rationale','')}".lower())

        # Recent missions
        mres = (
            c.raw_client.table("missions")
            .select("title,status,updated_at")
            .order("updated_at", desc=True)
            .limit(200)
            .execute()
        )
        for row in mres.data or []:
            texts.append(f"{row.get('title','')} {row.get('status','')}".lower())

    except Exception as exc:
        log.debug("[learning.patterns] fetch_recent_text failed: %s", exc)
    return texts


def detect_patterns(lookback_days: int = 30) -> list[OrganisationalPattern]:
    """Scan recent Command Memory for recurring organisational themes."""
    texts = _fetch_recent_text(lookback_days)
    if not texts:
        return []

    patterns: list[OrganisationalPattern] = []

    for theme, cfg in _THEME_SIGNALS.items():
        signals: list[str] = cfg["signals"]
        matched_signals: dict[str, int] = {}
        occurrences = 0

        for text in texts:
            hit = False
            for sig in signals:
                if sig in text:
                    matched_signals[sig] = matched_signals.get(sig, 0) + 1
                    hit = True
            if hit:
                occurrences += 1

        if occurrences >= _PATTERN_THRESHOLD:
            pattern = OrganisationalPattern(
                theme=theme,
                label=cfg["label"],
                occurrences=occurrences,
                window_days=lookback_days,
                signals_matched=sorted(matched_signals, key=matched_signals.get, reverse=True)[:4],
                inv_type=cfg["inv_type"],
            )
            patterns.append(pattern)
            _register_pattern(pattern)

    patterns.sort(key=lambda p: p.occurrences, reverse=True)
    log.info("[learning.patterns] Detected %d recurring pattern(s) over %dd window", len(patterns), lookback_days)
    return patterns


def _register_pattern(pattern: OrganisationalPattern) -> None:
    """Persist/update the pattern registry (dedup by theme)."""
    try:
        from command_memory_integration import log_decision_to_command_memory
        from tools.supabase.client import CommanderSupabaseClient

        owner = f"{PATTERN_OWNER_PREFIX}{pattern.theme}"

        # Update existing registry row if present
        try:
            c = CommanderSupabaseClient()
            if c.is_enabled() and c.raw_client:
                existing = (
                    c.raw_client.table("decisions")
                    .select("id")
                    .eq("owner", owner)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    c.raw_client.table("decisions").update({
                        "rationale": (
                            f"THEME: {pattern.theme} | OCCURRENCES: {pattern.occurrences} | "
                            f"WINDOW: {pattern.window_days}d | SIGNALS: {', '.join(pattern.signals_matched)} | "
                            f"SEVERITY: {pattern.severity} | DETECTED: {datetime.utcnow().isoformat()}"
                        ),
                    }).eq("id", existing.data[0]["id"]).execute()
                    return
        except Exception as exc:
            log.debug("[learning.patterns] Pattern update skipped: %s", exc)

        log_decision_to_command_memory(
            statement=(
                f"{_PATTERN_STATEMENT} {pattern.theme}: "
                f"{pattern.occurrences} occurrence(s) — {pattern.label}"
            ),
            rationale=(
                f"THEME: {pattern.theme} | OCCURRENCES: {pattern.occurrences} | "
                f"WINDOW: {pattern.window_days}d | SIGNALS: {', '.join(pattern.signals_matched)} | "
                f"SEVERITY: {pattern.severity} | DETECTED: {datetime.utcnow().isoformat()}"
            ),
            owner=owner,
        )
    except Exception as exc:
        log.debug("[learning.patterns] register_pattern failed: %s", exc)


def get_known_patterns(limit: int = 20) -> list[OrganisationalPattern]:
    """Return patterns from the registry."""
    try:
        from tools.supabase.client import CommanderSupabaseClient
        c = CommanderSupabaseClient()
        if not (c.is_enabled() and c.raw_client):
            return []

        res = (
            c.raw_client.table("decisions")
            .select("statement,rationale,owner,created_at")
            .like("owner", f"{PATTERN_OWNER_PREFIX}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        patterns: list[OrganisationalPattern] = []
        seen_themes: set[str] = set()
        for row in res.data or []:
            parts: dict[str, str] = {}
            for seg in str(row.get("rationale") or "").split(" | "):
                if ": " in seg:
                    k, v = seg.split(": ", 1)
                    parts[k.strip()] = v.strip()
            theme = parts.get("THEME", "")
            if not theme or theme in seen_themes:
                continue
            seen_themes.add(theme)
            cfg = _THEME_SIGNALS.get(theme, {})
            patterns.append(OrganisationalPattern(
                theme=theme,
                label=cfg.get("label", theme),
                occurrences=int(parts.get("OCCURRENCES", "0") or 0),
                window_days=int(str(parts.get("WINDOW", "30")).rstrip("d") or 30),
                signals_matched=parts.get("SIGNALS", "").split(", ") if parts.get("SIGNALS") else [],
                inv_type=cfg.get("inv_type", "operational"),
            ))
        return patterns

    except Exception as exc:
        log.debug("[learning.patterns] get_known_patterns failed: %s", exc)
        return []


# ── Pattern → Investigation ───────────────────────────────────────────────────

def pattern_to_investigation(pattern: OrganisationalPattern) -> str | None:
    """Open an investigation for a recurring pattern (Pattern → Investigation).

    Only meaningful for MEDIUM/HIGH severity patterns. Dedup is handled by the
    registry (same officer+type won't reopen).
    """
    if pattern.severity == "LOW":
        return None
    try:
        from lib.investigation.registry import open_investigation
        from lib.investigation.framework import InvestigationType

        try:
            inv_type = InvestigationType(pattern.inv_type)
        except ValueError:
            inv_type = InvestigationType.OPERATIONAL

        inv_id = open_investigation(
            question=(
                f"Why is '{pattern.label}' recurring "
                f"({pattern.occurrences} occurrences in {pattern.window_days}d)?"
            ),
            investigation_type=inv_type,
            source="pattern_recognition_engine:auto",
            officer="number_one",  # Number One owns cross-cutting patterns
            context=f"Pattern theme: {pattern.theme}. Signals: {', '.join(pattern.signals_matched)}.",
        )
        if inv_id:
            log.info("[learning.patterns] Pattern '%s' → investigation %s", pattern.theme, inv_id)
        return inv_id

    except Exception as exc:
        log.debug("[learning.patterns] pattern_to_investigation failed: %s", exc)
        return None


# ── Formatting ────────────────────────────────────────────────────────────────

def format_patterns(patterns: list[OrganisationalPattern]) -> str:
    if not patterns:
        return "_No recurring patterns detected._"
    lines = ["*Recurring Patterns:*"]
    for p in patterns[:6]:
        lines.append(
            f"  [{p.severity}] {p.label}: {p.occurrences}× in {p.window_days}d "
            f"({', '.join(p.signals_matched[:3])})"
        )
    return "\n".join(lines)


__all__ = [
    "OrganisationalPattern",
    "detect_patterns",
    "get_known_patterns",
    "pattern_to_investigation",
    "format_patterns",
    "PATTERN_OWNER_PREFIX",
]
