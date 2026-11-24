"""Tiered, incident-level morning brief view (default OFF).

Renders the clustered incidents (``incident_clustering``) and their delivery tiers (``delivery_tiers``) as brief lines: one entry per
INCIDENT (not per headline), each showing its lifecycle (NEW / SUBSEQUENT / RESTORATION_UPDATE / RELATED), and sections that follow
the tier (alerted and scheduled incidents in full, monitored candidates briefly, context and reference only as counts).

Flag: ``DELIVERY_TIERS_V1`` (``delivery_tiers.enabled()``), read at call time. ``captains_brief._evidence_lines`` only calls this when
it is on, so with the flag off the legacy ``brief_evidence.morning_view`` output is byte-for-byte unchanged (tests/test_tiered_brief.py).
Pure: no I/O, never sends anything. ``render`` also returns the event ids it showed so surfacing can be measured by id
(``brief_event_links``).
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

from intelligence import delivery_tiers as dt
from intelligence import incident_clustering as ic

RELATION_LABEL = {ic.NEW: "NEW", ic.SUBSEQUENT: "SUBSEQUENT", ic.RESTORATION_UPDATE: "RESTORATION", ic.RELATED: "RELATED",
                  ic.HISTORICAL_REFERENCE: "HISTORICAL"}
RESTORATION_LABEL = {"ongoing": "ongoing", "partially_restored": "partially restored", "restored": "restored", "unknown": "current status unknown"}
SECTION_FULL_LIMIT = 6
SECTION_MONITOR_LIMIT = 6
RECENT_HOURS = 72


def enabled() -> bool:
    return dt.enabled()


def _hhmm(t) -> str:
    return t.astimezone(timezone.utc).strftime("%d %b %H:%MZ") if t else "time unverified"


def _short(report_id: str) -> str:
    return str(report_id)[:8]


PORTAL_BASE_ENV = "PORTAL_BASE_URL"


def incident_id(inc: ic.Incident) -> str:
    """THE canonical incident id, used by the brief, Telegram alert payloads, Home, Decisions and the portal Intelligence page:
    'inc-' + sha1(earliest member report id | subject of that report)[:10]. Deterministic, and stable as later reports join (the earliest
    member does not change); two separate incidents never share it because report ids are unique."""
    first = min(inc.reports, key=lambda r: (r.candidate.published or datetime.max.replace(tzinfo=timezone.utc), r.event_id))
    subj = ",".join(sorted(ic.subjects(first.candidate.title)))
    return "inc-" + hashlib.sha1(f"{first.event_id}|{subj}".encode(), usedforsecurity=False).hexdigest()[:10]  # nosec B324 - identity hash


incident_key = incident_id          # the portal/DB column is named incident_key; same value


# Mirrors lcars-portal/src/lib/intelligenceLinks.ts (the single portal-side builder); tests/test_intelligence_links.py keeps them in step.
INTELLIGENCE_HOME_PATH = "/intelligence-workbench"
INCIDENTS_TAB = "incidents"
PRODUCTS_TAB = "products"


def intelligence_tab_link(tab: str, anchor: str = "", base: str | None = None) -> str:
    base = (os.getenv(PORTAL_BASE_ENV, "") if base is None else base).strip().rstrip("/")
    return f"{base}{INTELLIGENCE_HOME_PATH}?tab={tab}" + (f"#{anchor}" if anchor else "")


def incident_link(inc_id: str, base: str | None = None) -> str:
    """Contextual link to the one portal incident view every channel points at (Incidents tab of the Intelligence workbench, anchored on the incident)."""
    return intelligence_tab_link(INCIDENTS_TAB, inc_id, base)


def lifecycle_lines(inc: ic.Incident) -> list[str]:
    """Compact lifecycle: the NEW report, a count of SUBSEQUENT reports with the latest, each RESTORATION update and a RELATED count."""
    by = {rel: [r for r in inc.reports if r.relation == rel] for rel in ic.RELATIONS}
    lines = []
    for r in by[ic.NEW]:
        lines.append(f"    NEW {_hhmm(r.candidate.published)}: {r.candidate.title} [{_short(r.event_id)}]")
    subs = by[ic.SUBSEQUENT]
    if subs:
        last = subs[-1]
        lines.append(f"    SUBSEQUENT x{len(subs)}, latest {_hhmm(last.candidate.published)}: {last.candidate.title} [{_short(last.event_id)}]")
    for r in by[ic.RESTORATION_UPDATE]:
        kind = "partial" if r.restoration == "partial" else "full"
        lines.append(f"    RESTORATION ({kind}) {_hhmm(r.candidate.published)}: {r.candidate.title} [{_short(r.event_id)}]")
    if by[ic.RELATED]:
        lines.append(f"    RELATED x{len(by[ic.RELATED])} (commentary, cost, aftermath)")
    if by[ic.HISTORICAL_REFERENCE]:
        lines.append(f"    HISTORICAL x{len(by[ic.HISTORICAL_REFERENCE])} (refer back to an earlier event)")
    return lines


def _entry(inc: ic.Incident, td: dt.TierDecision) -> list[str]:
    head = f"- {inc.decision.headline.title} ({RESTORATION_LABEL.get(inc.restoration_status, inc.restoration_status)}; {inc.n_reports} reports; {incident_id(inc)})"
    return [head, f"    why: {td.reasons[0]}", f"    view: {incident_link(incident_id(inc))}", *lifecycle_lines(inc)]


def _brief_entry(inc: ic.Incident, td: dt.TierDecision) -> list[str]:
    state = RESTORATION_LABEL.get(inc.restoration_status, inc.restoration_status)
    return [f"- {inc.decision.headline.title} ({state}; {inc.n_reports} reports; {incident_id(inc)}) - {td.reasons[0]} [{incident_link(incident_id(inc))}]"]


def render(events: list[dict], *, now: datetime | None = None, window_hours: int = 72) -> tuple[list[str], list[str]]:
    """Return (lines, shown_event_ids). ``events``: dicts with id, title, source, collected_at, published_at (as ``brief_evidence`` reads)."""
    now = now or datetime.now(timezone.utc)
    incidents = ic.cluster_incidents(events, now=now, force=True)
    rows = [(inc, dt.tier_for_incident(inc, now=now)) for inc in incidents]
    cutoff = now - timedelta(hours=RECENT_HOURS)

    def recent(inc):
        times = [r.candidate.published for r in inc.reports if r.candidate.published]
        return bool(times) and max(times) >= cutoff

    by_tier = {t: [(i, d) for i, d in rows if d.tier == t and recent(i)] for t in dt.TIERS}
    newest_first = lambda pair: -max((r.candidate.published for r in pair[0].reports if r.candidate.published), default=datetime.min.replace(tzinfo=timezone.utc)).timestamp()
    for items in by_tier.values():
        items.sort(key=newest_first)
    lines = ["🛰 TIERED INCIDENT PICTURE (clustered by incident; lifecycle per report)",
             f"Based on reports from the last {window_hours} hours; incidents are consolidated, so one disruption is one entry.", ""]
    shown: list[str] = []

    def section(title, tier, limit, full):
        items = by_tier[tier][:limit]
        if not items:
            return False
        lines.append(title)
        for inc, td in items:
            lines.extend(_entry(inc, td) if full else _brief_entry(inc, td))
            shown.extend(r.event_id for r in inc.reports)
        if len(by_tier[tier]) > limit:
            lines.append(f"- ... and {len(by_tier[tier]) - limit} more in this tier")
        lines.append("")
        return True

    any_shown = section("ACTIVE ALERT-LEVEL INCIDENTS (live, stated impact, Australian relevance, solid evidence)", dt.IMMEDIATE_ALERT, SECTION_FULL_LIMIT, True)
    any_shown |= section("MATERIAL INCIDENTS FOR TODAY'S BRIEF", dt.SCHEDULED_BRIEF, SECTION_FULL_LIMIT, True)
    any_shown |= section("MONITORING (evidence not yet sufficient; will be re-tiered when it arrives)", dt.MONITOR, SECTION_MONITOR_LIMIT, False)
    if not any_shown:
        lines += ["No alert-level, scheduled or monitored incident in the window. This is not an all-clear: see the counts below.", ""]
    ctx, ref = len(by_tier[dt.CONTEXT]), len(by_tier[dt.REFERENCE_RETAIN])
    lines.append(f"Context only (supports an incident, no item of its own): {ctx}. Reference retained (no demonstrated Australian relevance or no stated consequence): {ref}.")
    return lines, sorted(set(shown))
