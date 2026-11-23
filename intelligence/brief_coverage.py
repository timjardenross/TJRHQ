"""Coverage block for the Morning brief (flag BRIEF_COVERAGE_V1[_MORNING], default OFF).

States what the brief actually looked at, so a quiet section is not mistaken for a quiet world: reports and publishers in the last 24h,
continuous sources that produced nothing, and the official warnings active in the Emergency Alert Hub (official wording, never
paraphrased). Deterministic and fail-soft: if a figure cannot be loaded the line says so rather than showing zero.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

MASTER_FLAG = "BRIEF_COVERAGE_V1"
MORNING_FLAG = "BRIEF_COVERAGE_V1_MORNING"
_TRUE = ("1", "true", "yes", "on")
PAGE_SIZE = 1000
MAX_PAGES = 6
MAX_SILENT_NAMED = 6

# Official severity wording, most severe first (matches intelligence/brief/external_domains.py)
_SEVERITY_ORDER = (("emergency_warning", "Emergency Warning"), ("watch_and_act", "Watch and Act"), ("advice", "Advice"), ("unknown", "Unknown severity"))
_KNOWN_SEVERITIES = frozenset(k for k, _ in _SEVERITY_ORDER)


def enabled() -> bool:
    def on(name):
        return os.getenv(name, "").strip().lower() in _TRUE
    return on(MASTER_FLAG) or on(MORNING_FLAG)


def _paged(sb_get, table: str, query: str, select: str) -> list[dict]:
    """All rows across pages. The caller treats an empty result as 'could not load', since a day always has reports."""
    out: list[dict] = []
    for page in range(MAX_PAGES):
        rows = sb_get(table, f"{query}&limit={PAGE_SIZE}&offset={page * PAGE_SIZE}&select={select}")
        out += rows or []
        if not rows or len(rows) < PAGE_SIZE:
            break
    return out


def collection_line(sb_get, now: datetime) -> str:
    since = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        registry = sb_get("intelligence_source_registry", "active=eq.true&select=source_id,source_name,content_expectation&limit=1000")
        events = _paged(sb_get, "intelligence_events", f"collected_at=gte.{since}&suppressed=eq.false", "source_id")
        if not registry or not events:
            return "- Collection: unavailable (source or report counts could not be loaded); do not read the sections below as quiet."
        reporting = {str(e.get("source_id")) for e in events}
        continuous = [r for r in registry if (r.get("content_expectation") or "continuous") == "continuous"]
        silent = sorted(r["source_name"] for r in continuous if str(r["source_id"]) not in reporting)
        line = f"- Collection: {len(events)} reports from {len(reporting)} of {len(registry)} active sources in the last 24h."
        if silent:
            named = ", ".join(silent[:MAX_SILENT_NAMED]) + (f" and {len(silent) - MAX_SILENT_NAMED} more" if len(silent) > MAX_SILENT_NAMED else "")
            line += f" {len(silent)} continuous sources produced nothing: {named}."
        return line
    except Exception:
        log.warning("coverage collection line unavailable", exc_info=True)
        return "- Collection: unavailable (the coverage check failed); do not read the sections below as quiet."


def warnings_line(load_alerts) -> str:
    """Active official warnings, counted by official severity. `load_alerts` raises on failure (store.load_active_emergency_alerts does)."""
    try:
        alerts = load_alerts(limit=500)
    except Exception:
        log.warning("coverage warnings line unavailable", exc_info=True)
        return "- Official warnings: unavailable (the Emergency Alert Hub could not be read); absence here is not an all-clear."
    if not alerts:
        return "- Official warnings: none active in the Emergency Alert Hub."
    counts: dict[str, int] = {}
    for a in alerts:
        sev = (a.get("severity") or "unknown").strip().lower()
        if sev not in _KNOWN_SEVERITIES:
            sev = "unknown"
        counts[sev] = counts.get(sev, 0) + 1
    parts = [f"{counts[k]} {label}" for k, label in _SEVERITY_ORDER if counts.get(k)]
    states = sorted({a.get("jurisdiction") for a in alerts if a.get("jurisdiction")})
    return f"- Official warnings active (Emergency Alert Hub): {', '.join(parts)}" + (f" across {', '.join(states)}." if states else ".")


def coverage_lines(sb_get, load_alerts, now: datetime | None = None) -> list[str]:
    """The block as plain text lines, or [] when the flag is off. Never raises."""
    if not enabled():
        return []
    try:
        now = now or datetime.now(timezone.utc)
        return ["COVERAGE (what this brief looked at)", collection_line(sb_get, now), warnings_line(load_alerts)]
    except Exception:
        log.warning("coverage block unavailable", exc_info=True)
        return ["COVERAGE", "- Unavailable (the coverage block failed); do not read the sections below as quiet."]
